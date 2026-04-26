"""Concrete :class:`LLMClient` backed by LiteLLM.

Why LiteLLM:
- One ``acompletion`` call routes to Anthropic / OpenAI / Bedrock / Gemini /
  vLLM with the same input/output shape — switching provider is a string
  edit, not a code change.
- :func:`litellm.completion_cost` is provider-aware so cost dashboards
  don't have to ship per-provider pricing tables.
- Langfuse callback integration is built-in (we still wire spans manually
  via ContextVar to preserve the Phase 3.5 trace hierarchy).

Brand isolation: the only files in the repo that import ``litellm`` are
this adapter and (optionally) :mod:`tools.llm.cost`. Everything else
depends on :class:`LLMClient` — swapping LiteLLM for Portkey or a custom
HTTP client is a one-file change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from tools.llm.client import LLMClient, OnTokenCallback
from tools.llm.cost import calculate_cost_usd
from tools.llm.errors import (
    LLMError,
    LLMTimeoutError,
    LLMValidationError,
    classify_provider_error,
)
from tools.llm.retry import with_retry
from tools.llm.types import LLMMessage, LLMRequest, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)

__all__ = ["LiteLLMClient"]

# How many times to re-prompt the model on JSON-schema validation failure.
# ONE retry — model usually fixes its output when shown the error. More
# becomes a tarpit.
_STRUCTURED_VALIDATION_RETRIES = 1


class LiteLLMClient(LLMClient):
    """LiteLLM-backed implementation of :class:`LLMClient`.

    The settings object is read once on construction; tests pass a stub
    settings + an ``acompletion_fn`` to bypass the real SDK. Production
    callers should use :func:`tools.llm.client.get_default_client`.
    """

    def __init__(
        self,
        *,
        settings: Any | None = None,
        acompletion_fn: Any | None = None,
        tracer: Any | None = None,
    ) -> None:
        # Lazy import keeps this module importable without LiteLLM (e.g. during
        # unit-test discovery on the dev host before ``poetry install``).
        if settings is None:
            from config.llm import get_llm_settings

            settings = get_llm_settings()
        self._settings = settings

        self._acompletion = acompletion_fn  # injected in tests; otherwise lazy
        if tracer is None:
            from tools.langfuse_client import get_tracer

            tracer = get_tracer()
        self._tracer = tracer

    # ---- public API ---------------------------------------------------- #

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return await self._invoke(request, stream=False, on_token=None)

    async def generate_stream(
        self,
        request: LLMRequest,
        *,
        on_token: OnTokenCallback | None = None,
    ) -> LLMResponse:
        return await self._invoke(request, stream=True, on_token=on_token)

    # ---- core path ----------------------------------------------------- #

    async def _invoke(
        self,
        request: LLMRequest,
        *,
        stream: bool,
        on_token: OnTokenCallback | None,
    ) -> LLMResponse:
        model = request.model or self._settings.resolved_model_for_tier(request.tier)
        provider = model.split("/", 1)[0] if "/" in model else "unknown"

        async def _attempt() -> LLMResponse:
            return await self._call_once(
                request=request,
                model=model,
                provider=provider,
                stream=stream,
                on_token=on_token,
            )

        # Structured-output retry loop wraps the transient-error retry loop
        # so a JSON validation miss gets one fresh attempt with the error
        # echoed back into the messages — the transient retry already
        # applied to each attempt.
        last_error: BaseException | None = None
        for attempt_idx in range(_STRUCTURED_VALIDATION_RETRIES + 1):
            try:
                response = await with_retry(
                    _attempt,
                    max_attempts=self._settings.max_retries,
                    initial_wait_s=self._settings.retry_initial_wait_s,
                    max_wait_s=self._settings.retry_max_wait_s,
                    op_name=f"llm.{request.node_name or 'call'}",
                )
            except LLMError:
                # Transient retry layer already gave up — propagate.
                raise

            if request.response_schema is None or response.parsed is not None:
                return response

            # Schema set but validation failed inside _call_once. Append
            # an assistant + user pair instructing a corrected JSON.
            last_error = ValueError("response did not satisfy response_schema")
            if attempt_idx >= _STRUCTURED_VALIDATION_RETRIES:
                break
            request = _augment_with_schema_error(request, response.text)

        raise LLMValidationError(
            f"response_schema validation failed after retries: {last_error}"
        )

    async def _call_once(
        self,
        *,
        request: LLMRequest,
        model: str,
        provider: str,
        stream: bool,
        on_token: OnTokenCallback | None,
    ) -> LLMResponse:
        sdk_messages = _build_sdk_messages(request)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": sdk_messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "timeout": request.timeout_s,
        }
        if request.response_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True
        # Deep tier: attach provider-specific reasoning kwargs. Empty dict
        # for providers without a uniform thinking API — the call still
        # runs on the provider's premium model, just without explicit
        # extended-thinking budget.
        if request.tier == "deep":
            kwargs.update(_deep_tier_kwargs(model))

        generation = self._start_generation(request=request, model=model, sdk_messages=sdk_messages)
        started = time.perf_counter()
        try:
            acompletion = self._resolve_acompletion()
            try:
                if stream:
                    aggregated_text, raw_response = await asyncio.wait_for(
                        self._consume_stream(acompletion, kwargs, on_token),
                        timeout=request.timeout_s,
                    )
                    response_text = aggregated_text
                else:
                    raw_response = await asyncio.wait_for(
                        acompletion(**kwargs),
                        timeout=request.timeout_s,
                    )
                    response_text = _extract_text(raw_response)
            except asyncio.TimeoutError as exc:
                raise LLMTimeoutError(f"LLM call exceeded {request.timeout_s}s") from exc
            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001 — every SDK exception lands here
                raise classify_provider_error(exc) from exc
        except Exception:
            generation.end(output=None, usage=None, metadata={"status": "error"})
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = _extract_usage(raw_response)
        cost_usd = calculate_cost_usd(
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            provider_response=raw_response,
        )

        # Optional structured-output validation. Don't raise here — let the
        # outer loop decide whether to retry with an error echo.
        parsed: BaseModel | None = None
        if request.response_schema is not None:
            parsed = _maybe_parse_schema(response_text, request.response_schema)

        result = LLMResponse(
            text=response_text,
            model=model,
            provider=provider,
            stop_reason=_extract_stop_reason(raw_response),
            usage=usage,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            parsed=parsed,
        )

        generation.end(
            output=result.text,
            usage=usage.model_dump(),
            metadata={
                "stop_reason": result.stop_reason,
                "cost_usd": result.cost_usd,
                "latency_ms": result.latency_ms,
            },
        )
        return result

    async def _consume_stream(
        self,
        acompletion: Any,
        kwargs: dict[str, Any],
        on_token: OnTokenCallback | None,
    ) -> tuple[str, Any]:
        """Iterate the LiteLLM async-generator, fan out tokens, return
        (aggregated_text, last_chunk_so_we_can_pull_usage_off_it)."""
        chunks: list[Any] = []
        text_parts: list[str] = []
        stream = await acompletion(**kwargs)
        try:
            async for chunk in stream:
                chunks.append(chunk)
                delta = _extract_delta(chunk)
                if not delta:
                    continue
                text_parts.append(delta)
                if on_token is not None:
                    try:
                        await on_token(delta)
                    except Exception as exc:  # noqa: BLE001 — streaming never blocks
                        logger.warning("llm.stream.on_token_error err=%s", exc)
        finally:
            close = getattr(stream, "aclose", None)
            if callable(close):
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass

        # The final chunk usually carries the usage/finish_reason; some
        # providers split it across chunks. Return the last chunk so the
        # extract_* helpers can dig.
        last_chunk = chunks[-1] if chunks else None
        return "".join(text_parts), last_chunk

    def _resolve_acompletion(self) -> Any:
        if self._acompletion is not None:
            return self._acompletion
        try:
            import litellm  # type: ignore[import-not-found]
        except ImportError as exc:
            raise LLMError(
                "litellm is not installed — run `poetry install` or inject "
                "acompletion_fn for tests"
            ) from exc
        self._acompletion = litellm.acompletion
        return self._acompletion

    def _start_generation(
        self,
        *,
        request: LLMRequest,
        model: str,
        sdk_messages: list[dict[str, Any]],
    ) -> Any:
        """Open a Langfuse generation under the active activity span.

        Mirrors :class:`tools.claude_client.ClaudeClient` so dashboards and
        traces from the LiteLLM path look identical to the legacy path.
        """
        from tools.langfuse_client import _NOOP_GEN, get_current_span

        span = get_current_span()
        if span is None:
            return _NOOP_GEN

        trace_id = request.trace_id or getattr(span, "trace_id", "") or ""
        return self._tracer.start_generation(
            trace_id=trace_id,
            parent_span=span,
            name=request.node_name or "llm_call",
            model=model,
            input_messages=sdk_messages,
            metadata=request.metadata or {},
        )


# ---------------------------------------------------------------------------
# Message building + response parsing helpers (pure functions for testability).
# ---------------------------------------------------------------------------


def _build_sdk_messages(request: LLMRequest) -> list[dict[str, Any]]:
    """Translate :class:`LLMMessage` list into LiteLLM's expected shape.

    For Anthropic + ``cache_policy=ephemeral`` the system message becomes
    a content-block list with ``cache_control={"type": "ephemeral"}``.
    LiteLLM forwards the block verbatim to Anthropic; for OpenAI the
    block is silently flattened to plain text and OpenAI's automatic
    5-minute cache window kicks in. Either way the call signature stays
    identical.
    """
    out: list[dict[str, Any]] = []
    for msg in request.messages:
        if msg.role == "system" and request.cache_policy == "ephemeral":
            out.append(
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": msg.content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            )
        else:
            out.append({"role": msg.role, "content": msg.content})
    return out


def _get_attr_or_key(obj: Any, name: str) -> Any:
    """Look up ``name`` on attribute *or* dict key — LiteLLM responses may be
    Pydantic models, plain dicts, or SDK objects depending on version."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _get_choices(obj: Any) -> list[Any]:
    choices = _get_attr_or_key(obj, "choices")
    return choices or []


def _extract_text(response: Any) -> str:
    """Pull the assistant text out of a LiteLLM ModelResponse."""
    choices = _get_choices(response)
    if not choices:
        return ""
    msg = _get_attr_or_key(choices[0], "message")
    if msg is None:
        return ""
    content = _get_attr_or_key(msg, "content")
    return content or ""


def _extract_delta(chunk: Any) -> str:
    """Extract the streaming delta from a LiteLLM stream chunk."""
    choices = _get_choices(chunk)
    if not choices:
        return ""
    delta = _get_attr_or_key(choices[0], "delta")
    if delta is None:
        return ""
    content = _get_attr_or_key(delta, "content")
    return content or ""


def _extract_stop_reason(response: Any) -> str | None:
    choices = _get_choices(response)
    if not choices:
        return None
    return _get_attr_or_key(choices[0], "finish_reason")


def _extract_usage(response: Any) -> TokenUsage:
    """Pull TokenUsage from a LiteLLM ModelResponse, including cache fields
    when the provider reports them."""
    if response is None:
        return TokenUsage()
    usage = _get_attr_or_key(response, "usage")
    if usage is None:
        return TokenUsage()

    def _read(name: str) -> int:
        value = _get_attr_or_key(usage, name)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    # Cache-token names: LiteLLM normalizes Anthropic's
    # cache_read_input_tokens / cache_creation_input_tokens onto the same
    # usage object. OpenAI's cached_tokens lives under
    # prompt_tokens_details — also surfaced when present.
    cache_read = _read("cache_read_input_tokens")
    cache_write = _read("cache_creation_input_tokens")
    if cache_read == 0:
        details = _get_attr_or_key(usage, "prompt_tokens_details")
        if details is not None:
            cache_read = int(_get_attr_or_key(details, "cached_tokens") or 0)

    return TokenUsage(
        input_tokens=_read("prompt_tokens"),
        output_tokens=_read("completion_tokens"),
        cache_read_tokens=int(cache_read or 0),
        cache_write_tokens=int(cache_write or 0),
    )


def _maybe_parse_schema(text: str, schema: type[BaseModel]) -> BaseModel | None:
    """Best-effort parse + validate against a Pydantic schema.

    Returns ``None`` on JSON parse error or schema validation error so the
    caller can decide whether to retry. Strips common code-fence noise
    (LLMs sometimes ignore the JSON-mode instruction and emit ```json
    fences anyway).
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`").lstrip("json").lstrip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()

    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    try:
        return schema.model_validate(payload)
    except ValidationError:
        return None


def _deep_tier_kwargs(model: str) -> dict[str, Any]:
    """Return provider-specific reasoning kwargs for ``tier="deep"``.

    Detection by model-string substring keeps the helper independent of
    the per-tier defaults table — a user override like
    ``LLM_MODEL_DEEP=openai/o3`` still picks up the right kwargs because
    the model name contains ``"o3"``.

    - OpenAI o-series (``o1`` / ``o3`` / ``o1-mini`` / ``o3-mini``):
      ``reasoning_effort="high"``.
    - Anthropic Opus (``claude-opus-*``): ``thinking={"type":"enabled",
      "budget_tokens":8000}``.
    - Other providers: empty dict — call still routes to the premium
      model from PROVIDER_DEFAULTS but with no reasoning knob.
    """
    from config.llm import DEEP_TIER_KWARGS

    short = model.split("/")[-1].lower()
    # OpenAI o-series — bare ``o1``/``o3`` or suffixed (``o1-mini``).
    if short.startswith("o1") or short.startswith("o3"):
        return dict(DEEP_TIER_KWARGS["openai_o_series"])
    if "opus" in short:
        return dict(DEEP_TIER_KWARGS["anthropic_opus"])
    return {}


def _augment_with_schema_error(request: LLMRequest, raw_text: str) -> LLMRequest:
    """Build a follow-up request that re-asks for valid JSON.

    Append:
    - assistant message with the previous bad output
    - user message instructing a strict JSON correction
    """
    error_msg = (
        "The previous response did not match the required JSON schema. "
        "Re-emit the answer as a single valid JSON object that matches "
        "the schema. Do not include explanations or code fences."
    )
    new_messages = list(request.messages) + [
        LLMMessage(role="assistant", content=raw_text),
        LLMMessage(role="user", content=error_msg),
    ]
    return request.model_copy(update={"messages": new_messages})
