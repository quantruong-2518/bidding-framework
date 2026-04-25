"""Backward-compat ClaudeClient surface — now wraps :class:`LLMClient` (Phase 3.7).

The Phase 2.2 agents (BA / SA / Domain) call this module's
:class:`ClaudeClient` with the legacy ``(model, system, messages)`` shape.
Internally every call is translated into an :class:`LLMRequest` and routed
through :func:`tools.llm.client.get_default_client` so the project picks up
LiteLLM-backed multi-provider support, retries, structured output, and cost
tracking without touching agent code.

Migration path:

- **3.7a** added :mod:`tools.llm` (the new abstraction).
- **3.7b** (this commit) makes :class:`ClaudeClient` a thin wrapper. Tests
  that mock ``ClaudeClient.generate`` continue to work; tests that asserted
  on the inner ``AsyncAnthropic`` SDK shape are removed (their ground is
  covered by ``tests/test_llm_client.py``).
- **3.7c** retires this module — agents import :class:`LLMClient` directly
  via DI and ``HAIKU``/``SONNET`` constants drop in favour of
  ``LLMRequest(role="extraction"|"reasoning")``.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from tools.llm import LLMClient, LLMMessage, LLMRequest, get_default_client
from tools.llm.types import LLMResponse

logger = logging.getLogger(__name__)

OnTokenCallback = Callable[[str], Awaitable[None]]

__all__ = [
    "ClaudeClient",
    "ClaudeResponse",
    "HAIKU",
    "SONNET",
    "OnTokenCallback",
]

# Anthropic model IDs — kept as the convenience constants existing agents
# import. LiteLLM accepts the bare ID and routes to Anthropic via its
# default provider table; the LLMRequest below sets ``model=model`` to
# preserve the legacy explicit-model behaviour. New code should prefer
# ``LLMRequest(role="extraction"|"reasoning")`` so a single env flip
# (``LLM_PROVIDER``) swaps the whole agent fleet.
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


class ClaudeResponse(BaseModel):
    """Legacy response shape. ``usage`` keys mirror Anthropic SDK names so
    the BA/SA/Domain agents can read ``response.usage["input_tokens"]``
    etc. without changes."""

    text: str
    model: str
    stop_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class ClaudeClient:
    """Compat shim — delegates to :class:`tools.llm.client.LLMClient`.

    Existing tests that ``patch("tools.claude_client.ClaudeClient.generate", ...)``
    continue to work: the patched method runs in place of this wrapper, so
    no LLM call happens. Tests that need to control the underlying LLM
    behaviour can pass an ``llm_client=`` directly (e.g. a
    :class:`tools.llm.fake.FakeLLMClient`).
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        llm_client: LLMClient | None = None,
        tracer: Any | None = None,
    ) -> None:
        if client is not None:
            # The pre-3.7 ClaudeClient took an ``AsyncAnthropic`` instance
            # for testability. The new wrapper exposes ``llm_client=`` for
            # the same purpose. Don't silently swallow the legacy kwarg —
            # callers should migrate to the explicit FakeLLMClient.
            logger.warning(
                "ClaudeClient(client=...) is ignored after Phase 3.7 — "
                "pass llm_client=FakeLLMClient(...) for tests instead."
            )
        # ``tracer`` was the Phase 3.5 LangfuseTracer hook; the LiteLLM
        # adapter now owns the generation lifecycle, so the kwarg is a
        # no-op here. Accepted for backward compat with tests that pass it.
        del tracer  # noqa: F841 — preserved for signature compat

        self._llm: LLMClient = llm_client or get_default_client()

    async def generate(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        *,
        cache_system: bool = True,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        trace_id: str | None = None,
        node_name: str | None = None,
    ) -> ClaudeResponse:
        request = _to_llm_request(
            model=model,
            system=system,
            messages=messages,
            cache_system=cache_system,
            max_tokens=max_tokens,
            temperature=temperature,
            trace_id=trace_id,
            node_name=node_name,
        )
        response = await self._llm.generate(request)
        return _to_claude_response(response)

    async def generate_stream(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        *,
        on_token: OnTokenCallback | None = None,
        cache_system: bool = True,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        trace_id: str | None = None,
        node_name: str | None = None,
    ) -> ClaudeResponse:
        request = _to_llm_request(
            model=model,
            system=system,
            messages=messages,
            cache_system=cache_system,
            max_tokens=max_tokens,
            temperature=temperature,
            trace_id=trace_id,
            node_name=node_name,
        )
        response = await self._llm.generate_stream(request, on_token=on_token)
        return _to_claude_response(response)


def _to_llm_request(
    *,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    cache_system: bool,
    max_tokens: int,
    temperature: float,
    trace_id: str | None,
    node_name: str | None,
) -> LLMRequest:
    """Translate the legacy positional model + (system, messages) shape into
    :class:`LLMRequest`. The system message is prepended; subsequent
    messages keep their roles."""
    llm_messages: list[LLMMessage] = [LLMMessage(role="system", content=system)]
    for m in messages:
        # Legacy callers always pass plain {"role": ..., "content": str}.
        llm_messages.append(LLMMessage(role=m["role"], content=m["content"]))

    # Map the model ID to a role so the LiteLLM adapter can still apply the
    # right defaults if the explicit `model` kwarg ever drops out — but
    # keep `model=model` so Phase 2.2 behaviour (always Anthropic) is
    # preserved bit-for-bit when no env override is set.
    role = "extraction" if "haiku" in model.lower() else "reasoning"

    return LLMRequest(
        messages=llm_messages,
        role=role,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        cache_policy="ephemeral" if cache_system else "none",
        trace_id=trace_id,
        node_name=node_name,
    )


def _to_claude_response(response: LLMResponse) -> ClaudeResponse:
    """Map :class:`LLMResponse` → legacy :class:`ClaudeResponse` shape.

    Usage keys revert to Anthropic SDK names so the BA/SA/Domain agents
    can keep reading ``response.usage["input_tokens"]`` etc. without a
    code change.
    """
    usage_dict: dict[str, int] = {}
    if response.usage.input_tokens:
        usage_dict["input_tokens"] = response.usage.input_tokens
    if response.usage.output_tokens:
        usage_dict["output_tokens"] = response.usage.output_tokens
    if response.usage.cache_read_tokens:
        usage_dict["cache_read_input_tokens"] = response.usage.cache_read_tokens
    if response.usage.cache_write_tokens:
        usage_dict["cache_creation_input_tokens"] = response.usage.cache_write_tokens
    return ClaudeResponse(
        text=response.text,
        model=response.model,
        stop_reason=response.stop_reason,
        usage=usage_dict,
    )
