"""Phase 3.5 Langfuse tracer — no-op wrapper + real SDK backing.

Instrumentation seam: :meth:`tools.claude_client.ClaudeClient.generate` +
:meth:`generate_stream`. The LangGraph nodes are unchanged — the tracer picks
up the activity-level span via :data:`_CURRENT_LLM_SPAN` (ContextVar) so each
generation is attached to its parent span without the agent graph carrying
extra kwargs.

Trace hierarchy emitted per bid workflow::

    trace(id=bid_id, name="bid-workflow", metadata={client,industry,profile,region})
    ├── span(name="ba_analysis", metadata={attempt})
    │   ├── generation(name="extract_requirements", model=HAIKU, ...)
    │   ├── generation(name="synthesize_draft",     model=SONNET, ...)
    │   └── generation(name="self_critique",        model=SONNET, ...)
    ├── span(name="sa_analysis") ...
    └── span(name="domain_mining") ...

Design notes:

- No-op fallback: when :attr:`LangfuseSettings.secret_key` is absent the tracer
  returns :class:`_NoopSpan` / :class:`_NoopGeneration`. They share the same
  method surface so callers need no branching.
- Trace-ID convention: ``trace_id = str(bid_id)``. Activities derive it from
  their input — no workflow-side Langfuse call (keeps determinism).
- Streaming: the aggregate generation captures the final text + usage after
  ``messages.stream`` closes. Mid-stream token deltas stay on the Phase 2.5
  Redis path.
- ``aclose``: activity wrappers call it in ``finally`` so the Langfuse SDK's
  background flusher drains before the activity returns.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Protocol

from config.langfuse import LangfuseSettings, get_langfuse_settings

logger = logging.getLogger(__name__)

__all__ = [
    "LangfuseTracer",
    "LangfuseSpan",
    "LangfuseGeneration",
    "span_context",
    "get_current_span",
    "get_tracer",
]


class LangfuseSpan(Protocol):
    """Common surface used by callers; both real + noop span satisfy it."""

    trace_id: str

    def end(self, *, metadata: dict[str, Any] | None = None) -> None: ...


class LangfuseGeneration(Protocol):
    """Common surface for a generation record (wraps a single LLM call)."""

    trace_id: str

    def end(
        self,
        *,
        output: str | None = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


_CURRENT_LLM_SPAN: contextvars.ContextVar["LangfuseSpan | None"] = contextvars.ContextVar(
    "langfuse_current_span", default=None
)


def get_current_span() -> LangfuseSpan | None:
    """Return the Langfuse span bound to the current async context, or ``None``."""
    return _CURRENT_LLM_SPAN.get()


class _NoopGeneration:
    """Zero-cost generation stand-in used when tracing is disabled."""

    trace_id: str = ""

    def end(
        self,
        *,
        output: str | None = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None


class _NoopSpan:
    """Zero-cost span stand-in used when tracing is disabled."""

    trace_id: str = ""

    def end(self, *, metadata: dict[str, Any] | None = None) -> None:
        return None


_NOOP_SPAN = _NoopSpan()
_NOOP_GEN = _NoopGeneration()


class _RealSpan:
    """Wraps a Langfuse SDK ``StatefulSpanClient`` with a minimal surface."""

    def __init__(self, handle: Any, trace_id: str) -> None:
        self._handle = handle
        self.trace_id = trace_id

    @property
    def handle(self) -> Any:
        return self._handle

    def end(self, *, metadata: dict[str, Any] | None = None) -> None:
        try:
            if metadata is not None:
                self._handle.update(metadata=metadata)
            self._handle.end()
        except Exception as exc:  # noqa: BLE001 — observability never blocks
            logger.warning("langfuse.span.end_failed err=%s", exc)


class _RealGeneration:
    """Wraps a Langfuse SDK ``StatefulGenerationClient`` with a minimal surface."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def end(
        self,
        *,
        output: str | None = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._handle.end(output=output, usage=usage, metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            logger.warning("langfuse.generation.end_failed err=%s", exc)


class LangfuseTracer:
    """Thin facade over the Langfuse SDK with no-op fallback.

    Activities call :meth:`start_span` with ``trace_id=str(bid_id)`` so every
    LLM call fires under a single trace regardless of which activity created
    the span. :meth:`start_generation` is invoked from :class:`ClaudeClient`
    via :func:`get_current_span`.
    """

    def __init__(
        self,
        settings: LangfuseSettings | None = None,
        client: Any | None = None,
    ) -> None:
        self._settings = settings or get_langfuse_settings()
        self._client = client  # injected in tests
        self._client_resolved = client is not None

    @property
    def enabled(self) -> bool:
        """True when a Langfuse SDK client is available AND secret_key is set."""
        return bool(self._settings.secret_key)

    def _get_client(self) -> Any | None:
        if self._client_resolved:
            return self._client
        self._client_resolved = True
        if not self.enabled:
            self._client = None
            return None
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self._settings.public_key,
                secret_key=self._settings.secret_key,
                host=self._settings.host,
                release=self._settings.release,
            )
        except Exception as exc:  # noqa: BLE001 — tracer must not crash the app
            logger.warning("langfuse.client.init_failed err=%s", exc)
            self._client = None
        return self._client

    def start_span(
        self,
        *,
        trace_id: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> LangfuseSpan:
        """Start a span under ``trace_id``; returns a no-op span when disabled."""
        client = self._get_client()
        if client is None:
            return _NOOP_SPAN
        try:
            handle = client.span(
                trace_id=trace_id,
                name=name,
                metadata=metadata or {},
            )
            return _RealSpan(handle, trace_id=trace_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("langfuse.span.start_failed name=%s err=%s", name, exc)
            return _NOOP_SPAN

    def start_generation(
        self,
        *,
        trace_id: str,
        parent_span: LangfuseSpan | None,
        name: str,
        model: str,
        input_messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> LangfuseGeneration:
        """Start a generation attached to ``parent_span`` (or trace root)."""
        client = self._get_client()
        if client is None:
            return _NOOP_GEN
        try:
            parent_handle = (
                parent_span.handle  # type: ignore[attr-defined]
                if isinstance(parent_span, _RealSpan)
                else None
            )
            kwargs: dict[str, Any] = {
                "trace_id": trace_id,
                "name": name,
                "model": model,
                "input": input_messages,
                "metadata": metadata or {},
            }
            if parent_handle is not None:
                kwargs["parent_observation_id"] = getattr(parent_handle, "id", None)
            handle = client.generation(**kwargs)
            return _RealGeneration(handle)
        except Exception as exc:  # noqa: BLE001
            logger.warning("langfuse.generation.start_failed name=%s err=%s", name, exc)
            return _NOOP_GEN

    async def aclose(self) -> None:
        """Flush buffered events to Langfuse; safe to call when disabled."""
        client = self._client if self._client_resolved else None
        if client is None:
            return
        try:
            flush = getattr(client, "flush", None)
            if callable(flush):
                flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("langfuse.flush_failed err=%s", exc)


@asynccontextmanager
async def span_context(span: LangfuseSpan) -> AsyncIterator[LangfuseSpan]:
    """Bind ``span`` to :data:`_CURRENT_LLM_SPAN` for the lifetime of the block."""
    token = _CURRENT_LLM_SPAN.set(span)
    try:
        yield span
    finally:
        _CURRENT_LLM_SPAN.reset(token)


def get_tracer() -> LangfuseTracer:
    """Return a fresh :class:`LangfuseTracer` bound to the global settings."""
    return LangfuseTracer()
