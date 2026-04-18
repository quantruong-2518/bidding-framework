"""Thin AsyncAnthropic wrapper with ephemeral prompt caching on system prompts."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from config.claude import HAIKU, SONNET, get_claude_settings
from tools.langfuse_client import LangfuseTracer, get_current_span, get_tracer

logger = logging.getLogger(__name__)

OnTokenCallback = Callable[[str], Awaitable[None]]

__all__ = [
    "ClaudeClient",
    "ClaudeResponse",
    "HAIKU",
    "SONNET",
    "OnTokenCallback",
]


class ClaudeResponse(BaseModel):
    """Normalized Claude completion result with token usage counters."""

    text: str
    model: str
    stop_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class ClaudeClient:
    """AsyncAnthropic wrapper enforcing the Task 1.3 caching + routing contract."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        tracer: LangfuseTracer | None = None,
    ) -> None:
        self._client = client  # lazy; injected in tests
        self._settings = get_claude_settings()
        # Phase 3.5 — observability. Tracer is a no-op when `LANGFUSE_SECRET_KEY`
        # is absent, so default callers pay zero overhead.
        self._tracer = tracer or get_tracer()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropic

        kwargs: dict[str, Any] = {
            "timeout": self._settings.timeout_seconds,
            "max_retries": self._settings.max_retries,
        }
        if self._settings.api_key:
            kwargs["api_key"] = self._settings.api_key
        if self._settings.base_url:
            kwargs["base_url"] = self._settings.base_url
        self._client = AsyncAnthropic(**kwargs)
        return self._client

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
        """Send a Messages request; cache the system prompt via `cache_control` when enabled.

        Phase 3.5 — when a Langfuse span is bound to the current async context
        (activity wrappers call :func:`span_context`), this method opens a
        child ``generation`` record on Langfuse and closes it with the final
        text + usage. No-op when the tracer is disabled.
        """
        client = self._get_client()

        system_payload: list[dict[str, Any]] | str
        if cache_system:
            system_payload = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_payload = system

        logger.debug(
            "claude.request model=%s msgs=%d cache_system=%s",
            model,
            len(messages),
            cache_system,
        )
        generation = self._start_generation(
            trace_id=trace_id,
            node_name=node_name,
            model=model,
            messages=messages,
        )
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_payload,
                messages=messages,
            )
        except Exception:
            generation.end(output=None, usage=None, metadata={"status": "error"})
            raise

        claude_response = _to_claude_response(response)
        generation.end(
            output=claude_response.text,
            usage=claude_response.usage or None,
            metadata={"stop_reason": claude_response.stop_reason} if claude_response.stop_reason else None,
        )
        return claude_response

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
        """Stream tokens to ``on_token`` as they arrive; return the final completion.

        Mirrors :meth:`generate` — same prompt caching wiring, same final
        :class:`ClaudeResponse` shape — but uses Anthropic's ``messages.stream``
        API under the hood so callers can forward each ``text_delta`` to a
        sink (e.g. the Phase 2.5 :class:`TokenPublisher`) before the model
        finishes. The BA/SA/Domain agents still parse the returned
        ``response.text`` as JSON after streaming completes, so this method
        preserves their existing control flow.
        """
        client = self._get_client()

        system_payload: list[dict[str, Any]] | str
        if cache_system:
            system_payload = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_payload = system

        logger.debug(
            "claude.stream.request model=%s msgs=%d cache_system=%s",
            model,
            len(messages),
            cache_system,
        )
        generation = self._start_generation(
            trace_id=trace_id,
            node_name=node_name,
            model=model,
            messages=messages,
            metadata={"streaming": True},
        )
        try:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_payload,
                messages=messages,
            ) as stream:
                async for text_delta in stream.text_stream:
                    if not text_delta:
                        continue
                    if on_token is not None:
                        try:
                            await on_token(text_delta)
                        except Exception as exc:  # noqa: BLE001 — streaming never blocks
                            logger.warning("claude.stream.on_token_error err=%s", exc)
                final_message = await stream.get_final_message()
        except Exception:
            generation.end(output=None, usage=None, metadata={"status": "error"})
            raise

        claude_response = _to_claude_response(final_message)
        generation.end(
            output=claude_response.text,
            usage=claude_response.usage or None,
            metadata={"stop_reason": claude_response.stop_reason} if claude_response.stop_reason else None,
        )
        return claude_response

    def _start_generation(
        self,
        *,
        trace_id: str | None,
        node_name: str | None,
        model: str,
        messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Open a Langfuse generation when a span is bound; returns a noop otherwise."""
        span = get_current_span()
        if span is None:
            # Without a parent span we have no trace_id fallback for free-floating
            # calls (e.g. unit tests). Fall through to noop.
            from tools.langfuse_client import _NOOP_GEN  # local import — avoid cycles

            return _NOOP_GEN
        resolved_trace_id = trace_id or getattr(span, "trace_id", "") or ""
        return self._tracer.start_generation(
            trace_id=resolved_trace_id,
            parent_span=span,
            name=node_name or "llm_call",
            model=model,
            input_messages=messages,
            metadata=metadata or {},
        )


def _to_claude_response(response: Any) -> ClaudeResponse:
    """Normalize SDK response objects (and mocks) into a ClaudeResponse."""
    text_parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else ""
            )
            if text:
                text_parts.append(text)

    usage_obj = getattr(response, "usage", None)
    usage_dict: dict[str, int] = {}
    if usage_obj is not None:
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            value = getattr(usage_obj, key, None)
            if value is None and isinstance(usage_obj, dict):
                value = usage_obj.get(key)
            if value is not None:
                usage_dict[key] = int(value)

    return ClaudeResponse(
        text="".join(text_parts),
        model=getattr(response, "model", "") or "",
        stop_reason=getattr(response, "stop_reason", None),
        usage=usage_dict,
    )
