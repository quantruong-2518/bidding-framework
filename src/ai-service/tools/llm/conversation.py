"""Stateful multi-turn conversation that swaps tier per call.

The Phase 3.7d use-case: one logical conversation flows through several
agent steps of varying complexity — extract keywords (``nano``), group
into themes (``small``), critique the grouping (``flagship``), draft a
multi-phase plan (``deep`` with extended thinking) — while the message
history is preserved so each step sees what came before.

Memory is provider-agnostic by construction: every message is plain
text, so the conversation remains coherent even when consecutive turns
land on different providers (Anthropic Sonnet → OpenAI gpt-4o-mini →
Anthropic Opus thinking, all in one ``LLMConversation``).

Caveats — flagged here, not silently handled:

- **Prompt cache miss on tier swap.** Anthropic / OpenAI ephemeral
  caches are keyed per-model. Bouncing tiers means each turn pays the
  full input-token cost. For long system prompts, group consecutive
  turns at the same tier when feasible.
- **No auto-summarize.** When the running history outgrows the smallest
  model's context window, the call will fail with the provider's
  context-length error. Use :meth:`compact` (opt-in) to drop or
  summarize old turns before the next ``send``.
- **Tool / function calls** aren't part of this v1 surface — turns are
  text-in / text-out only. Add structured-output shaping per call via
  ``LLMRequest.response_schema`` once a typed contract is needed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from tools.llm.client import LLMClient, OnTokenCallback, get_default_client
from tools.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMTier

logger = logging.getLogger(__name__)

__all__ = ["LLMConversation", "ConversationTurn"]


@dataclass
class ConversationTurn:
    """One round-trip's audit trail. Persisted on the conversation so
    callers can inspect cost / model usage after the fact without
    re-running the LLM."""

    tier: LLMTier
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    latency_ms: int
    user_content: str = ""
    assistant_content: str = ""


@dataclass
class LLMConversation:
    """Multi-turn LLM session with cross-model memory.

    Construct once per logical conversation::

        conv = LLMConversation(
            system="You are a senior bid analyst.",
            client=get_default_client(),
        )
        await conv.send("Extract 5 keywords from this RFP", tier="nano")
        await conv.send("Group them into themes",            tier="small")
        await conv.send("Critique the grouping",              tier="flagship")
        await conv.send("Plan a 3-phase rollout",             tier="deep")
        print(conv.total_cost_usd, [t.tier for t in conv.turns])

    The conversation owns ``messages`` (the full chat history) and
    ``turns`` (per-call audit). Both are public — callers can read,
    mutate (carefully), or serialize for resume across processes.
    """

    system: str | None = None
    client: LLMClient | None = None
    # Tier used when ``send()`` is called without an explicit tier kwarg.
    default_tier: LLMTier = "flagship"
    default_max_tokens: int = 2048
    default_temperature: float = 0.3
    default_cache_policy: Literal["ephemeral", "none"] = "ephemeral"
    default_timeout_s: float | None = None
    # Trace propagation — when set, every turn's underlying LLMRequest
    # carries this trace_id so Langfuse links them under one trace.
    trace_id: str | None = None

    messages: list[LLMMessage] = field(default_factory=list)
    turns: list[ConversationTurn] = field(default_factory=list)

    # Serializes send()/send_stream()/compact() so concurrent calls cannot
    # interleave user/assistant messages or compact history mid-flight.
    # Created per-instance, not shared.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = get_default_client()
        if self.system and not self.messages:
            self.messages.append(LLMMessage(role="system", content=self.system))

    @property
    def _llm(self) -> LLMClient:
        # ``client`` is annotated Optional for ergonomic construction
        # (callers can omit it and let the default-client wire up). After
        # ``__post_init__`` it's always set; this property narrows the
        # type so call sites don't need ``# type: ignore`` noise.
        assert self.client is not None, "client set in __post_init__"
        return self.client

    # ------------------------------------------------------------------ #
    # Sending turns
    # ------------------------------------------------------------------ #

    async def send(
        self,
        content: str,
        *,
        tier: LLMTier | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        cache_policy: Literal["ephemeral", "none"] | None = None,
        response_schema: type[BaseModel] | None = None,
        node_name: str | None = None,
    ) -> LLMResponse:
        """Append a user message, call the LLM, append the assistant reply.

        Returns the full :class:`LLMResponse` (text, usage, cost, parsed
        schema, latency). The user/assistant messages are appended to
        ``self.messages`` regardless of LLM outcome so retries see the
        same history — except on raised exceptions, where the in-flight
        user message is rolled back so the next ``send`` doesn't dangle
        an unanswered turn.
        """
        async with self._lock:
            request = self._build_request(
                user_content=content,
                tier=tier or self.default_tier,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                cache_policy=cache_policy,
                response_schema=response_schema,
                node_name=node_name,
            )
            # Append user before the call so streaming/midflight readers see it.
            user_msg = LLMMessage(role="user", content=content)
            self.messages.append(user_msg)
            try:
                response = await self._llm.generate(request)
            except BaseException:
                # Roll back the unanswered user turn so retries don't double up.
                self.messages.pop()
                raise

            self._record_turn(request, response, content)
            return response

    async def send_stream(
        self,
        content: str,
        *,
        on_token: OnTokenCallback | None,
        tier: LLMTier | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        cache_policy: Literal["ephemeral", "none"] | None = None,
        node_name: str | None = None,
    ) -> LLMResponse:
        """Streaming variant of :meth:`send`. Schema-validated output is
        not supported on the streaming path (the same restriction as the
        underlying adapter)."""
        async with self._lock:
            request = self._build_request(
                user_content=content,
                tier=tier or self.default_tier,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                cache_policy=cache_policy,
                response_schema=None,
                node_name=node_name,
            )
            self.messages.append(LLMMessage(role="user", content=content))
            try:
                response = await self._llm.generate_stream(
                    request, on_token=on_token
                )
            except BaseException:
                self.messages.pop()
                raise

            self._record_turn(request, response, content)
            return response

    def _build_request(
        self,
        *,
        user_content: str,
        tier: LLMTier,
        model: str | None,
        max_tokens: int | None,
        temperature: float | None,
        cache_policy: Literal["ephemeral", "none"] | None,
        response_schema: type[BaseModel] | None,
        node_name: str | None,
    ) -> LLMRequest:
        """Compose the LLMRequest with the new user message included.

        We pass ``messages = self.messages + [user_msg]`` (rather than
        appending then snapshotting) so a parallel ``compact()`` call
        can't race with request building. The actual append happens in
        ``send()`` after this returns.
        """
        next_messages = list(self.messages) + [
            LLMMessage(role="user", content=user_content)
        ]
        kwargs: dict[str, Any] = {
            "messages": next_messages,
            "tier": tier,
            "model": model,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "cache_policy": cache_policy or self.default_cache_policy,
            "response_schema": response_schema,
            "trace_id": self.trace_id,
            "node_name": node_name,
        }
        if self.default_timeout_s is not None:
            kwargs["timeout_s"] = self.default_timeout_s
        return LLMRequest(**kwargs)

    def _record_turn(
        self,
        request: LLMRequest,
        response: LLMResponse,
        user_content: str,
    ) -> None:
        self.messages.append(LLMMessage(role="assistant", content=response.text))
        self.turns.append(
            ConversationTurn(
                tier=request.tier,
                model=response.model,
                provider=response.provider,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_read_tokens=response.usage.cache_read_tokens,
                cost_usd=response.cost_usd,
                latency_ms=response.latency_ms,
                user_content=user_content,
                assistant_content=response.text,
            )
        )

    # ------------------------------------------------------------------ #
    # Compaction (opt-in escape hatch — never auto-triggered)
    # ------------------------------------------------------------------ #

    async def compact(
        self,
        *,
        strategy: Literal["head_tail", "summarize"] = "head_tail",
        keep_last_n: int = 4,
        summary_tier: LLMTier = "nano",
    ) -> None:
        """Shrink the running history to fit a smaller-model context window.

        Holds :attr:`_lock` for the duration so a concurrent ``send`` cannot
        observe a half-rewritten history. Under ``summarize`` that means
        new turns wait until the summary LLM call completes.

        Strategies:

        - ``head_tail`` ($0): keeps the system prompt + the last
          ``keep_last_n`` messages. Loses middle context entirely. Use
          when the early turns are setup the model doesn't need to recall
          verbatim (e.g. the original RFP text was already extracted).
        - ``summarize`` (~$0.0001/call on nano): replaces middle turns
          with a single ``system``-role summary message. Preserves intent
          but loses precision — verify summary captures any compliance /
          contractual specifics before trusting downstream output. NOTE:
          dropped middle is sent as one prompt; if it exceeds the
          summary tier's context window the call fails. v1 doesn't chunk —
          callers with very long histories should compact early.
        """
        async with self._lock:
            if len(self.messages) <= keep_last_n + 1:
                return  # nothing to compact

            head: list[LLMMessage] = []
            rest = self.messages
            if rest and rest[0].role == "system":
                head = [rest[0]]
                rest = rest[1:]

            cut = max(0, len(rest) - keep_last_n)
            if cut == 0:
                return
            dropped, tail = rest[:cut], rest[cut:]

            if strategy == "head_tail":
                self.messages = head + tail
                logger.info(
                    "conv.compact head_tail dropped=%d kept=%d",
                    len(dropped),
                    len(tail),
                )
                return

            # summarize strategy — call the LLM to compress dropped turns.
            summary_text = "\n\n".join(f"{m.role}: {m.content}" for m in dropped)
            prompt = (
                "Summarize the following conversation excerpt into 3-6 bullet points. "
                "Preserve names, numbers, dates, and any explicit requirements. "
                "Output bullets only — no preamble.\n\n"
                f"{summary_text}"
            )
            summary_request = LLMRequest(
                messages=[LLMMessage(role="user", content=prompt)],
                tier=summary_tier,
                max_tokens=512,
                temperature=0.0,
                cache_policy="none",  # one-shot; cache adds no value
                trace_id=self.trace_id,
                node_name="conversation.compact.summarize",
            )
            summary_response = await self._llm.generate(summary_request)
            summary_msg = LLMMessage(
                role="system",
                content=f"[earlier-context-summary]\n{summary_response.text}",
            )
            self.messages = head + [summary_msg] + tail
            logger.info(
                "conv.compact summarize dropped=%d kept=%d cost_usd=%.6f",
                len(dropped),
                len(tail),
                summary_response.cost_usd,
            )

    # ------------------------------------------------------------------ #
    # Read-only audit accessors
    # ------------------------------------------------------------------ #

    @property
    def total_cost_usd(self) -> float:
        return round(sum(t.cost_usd for t in self.turns), 6)

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    @property
    def total_output_tokens(self) -> int:
        return sum(t.output_tokens for t in self.turns)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for resume / persistence. Round-trips with
        :meth:`from_dict`. Skips the live ``client`` instance — caller
        wires it back on revive."""
        return {
            "system": self.system,
            "default_tier": self.default_tier,
            "trace_id": self.trace_id,
            "messages": [m.model_dump() for m in self.messages],
            "turns": [t.__dict__ for t in self.turns],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        client: LLMClient | None = None,
    ) -> "LLMConversation":
        """Revive a conversation from :meth:`to_dict` output.

        **Trust boundary**: ``data`` is treated as caller-controlled and
        baked into the running history verbatim. Do NOT call this with a
        payload from an untrusted source (e.g. a different tenant's
        stored conversation, or user-uploaded JSON) without first
        sanitising ``data["messages"]`` — a malicious payload can plant
        an arbitrary ``system``-role message containing prompt-injection
        instructions that subsequent ``send`` calls will obey.

        Safe sources: same-tenant persisted snapshots, in-process retry
        logic, test fixtures.
        """
        conv = cls(
            system=data.get("system"),
            client=client,
            default_tier=data.get("default_tier", "flagship"),
            trace_id=data.get("trace_id"),
        )
        # Replace the system-seeded messages with the persisted history.
        conv.messages = [LLMMessage(**m) for m in data.get("messages", [])]
        conv.turns = [ConversationTurn(**t) for t in data.get("turns", [])]
        return conv
