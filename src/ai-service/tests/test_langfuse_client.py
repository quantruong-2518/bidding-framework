"""Phase 3.5 Langfuse tracer tests — no-op fallback + real SDK path.

The autouse ``_disable_langfuse_by_default`` fixture scrubs ``LANGFUSE_*``
env vars so :meth:`LangfuseTracer.enabled` is False by default. Enabled-path
tests opt in by monkeypatching settings + injecting a mock client.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from config.langfuse import LangfuseSettings
from tools.langfuse_client import (
    LangfuseTracer,
    get_current_span,
    span_context,
)


@pytest.mark.asyncio
async def test_tracer_disabled_returns_noop_span_and_generation() -> None:
    tracer = LangfuseTracer(settings=LangfuseSettings())

    assert tracer.enabled is False
    span = tracer.start_span(trace_id="bid-123", name="ba_analysis")
    gen = tracer.start_generation(
        trace_id="bid-123",
        parent_span=span,
        name="extract_requirements",
        model="claude-haiku-4-5-20251001",
        input_messages=[{"role": "user", "content": "x"}],
    )

    # Noop surface accepts all kwargs without raising.
    span.end(metadata={"attempt": 1})
    gen.end(output="ok", usage={"input_tokens": 1}, metadata={"node": "extract"})
    await tracer.aclose()


@pytest.mark.asyncio
async def test_span_context_binds_to_contextvar_and_clears() -> None:
    tracer = LangfuseTracer(settings=LangfuseSettings())
    span = tracer.start_span(trace_id="bid-1", name="ba_analysis")

    assert get_current_span() is None
    async with span_context(span):
        assert get_current_span() is span
    assert get_current_span() is None


@pytest.mark.asyncio
async def test_tracer_disabled_aclose_is_idempotent_and_no_client() -> None:
    tracer = LangfuseTracer(settings=LangfuseSettings())
    # Never calls the SDK; flush is a no-op.
    await tracer.aclose()
    await tracer.aclose()


@pytest.mark.asyncio
async def test_tracer_enabled_calls_span_and_generation_sdk_methods() -> None:
    settings = LangfuseSettings(
        public_key="pk-test",
        secret_key="sk-test",
        host="http://langfuse:3000",
    )
    fake_span = SimpleNamespace(id="span-1", update=MagicMock(), end=MagicMock())
    fake_gen = SimpleNamespace(end=MagicMock())
    fake_client = MagicMock()
    fake_client.span = MagicMock(return_value=fake_span)
    fake_client.generation = MagicMock(return_value=fake_gen)
    fake_client.flush = MagicMock()

    tracer = LangfuseTracer(settings=settings, client=fake_client)
    assert tracer.enabled is True

    span = tracer.start_span(
        trace_id="bid-42",
        name="ba_analysis",
        metadata={"attempt": 2},
    )
    gen = tracer.start_generation(
        trace_id="bid-42",
        parent_span=span,
        name="extract_requirements",
        model="claude-haiku-4-5-20251001",
        input_messages=[{"role": "user", "content": "hi"}],
        metadata={"phase": "3.5"},
    )

    fake_client.span.assert_called_once()
    span_kwargs = fake_client.span.call_args.kwargs
    assert span_kwargs["trace_id"] == "bid-42"
    assert span_kwargs["name"] == "ba_analysis"
    assert span_kwargs["metadata"] == {"attempt": 2}

    fake_client.generation.assert_called_once()
    gen_kwargs = fake_client.generation.call_args.kwargs
    assert gen_kwargs["trace_id"] == "bid-42"
    assert gen_kwargs["name"] == "extract_requirements"
    assert gen_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert gen_kwargs["parent_observation_id"] == "span-1"

    gen.end(output="result", usage={"input_tokens": 5, "output_tokens": 7})
    fake_gen.end.assert_called_once_with(
        output="result", usage={"input_tokens": 5, "output_tokens": 7}, metadata=None
    )

    span.end(metadata={"ok": True})
    fake_span.update.assert_called_once_with(metadata={"ok": True})
    fake_span.end.assert_called_once()

    await tracer.aclose()
    fake_client.flush.assert_called_once()


@pytest.mark.asyncio
async def test_tracer_enabled_sdk_errors_degrade_to_noop() -> None:
    settings = LangfuseSettings(
        public_key="pk-test",
        secret_key="sk-test",
    )
    fake_client = MagicMock()
    fake_client.span = MagicMock(side_effect=RuntimeError("boom"))
    fake_client.generation = MagicMock(side_effect=RuntimeError("boom"))

    tracer = LangfuseTracer(settings=settings, client=fake_client)

    span = tracer.start_span(trace_id="bid-1", name="ba_analysis")
    gen = tracer.start_generation(
        trace_id="bid-1",
        parent_span=span,
        name="extract_requirements",
        model="haiku",
        input_messages=[],
    )
    # Both degraded to noop; calling .end must not raise.
    span.end()
    gen.end(output="x")
