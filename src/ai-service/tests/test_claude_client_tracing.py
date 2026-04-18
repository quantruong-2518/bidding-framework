"""Phase 3.5 — ClaudeClient creates Langfuse generations when a span is bound.

The autouse fixtures in conftest scrub ``LANGFUSE_SECRET_KEY`` so the default
tracer resolves to the no-op path. These tests inject a mock tracer directly
into :class:`ClaudeClient` + bind a fake span via :func:`span_context` to
exercise the instrumentation without touching the Langfuse SDK.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tools.claude_client import ClaudeClient
from tools.langfuse_client import _NoopSpan, span_context


class _StubMessages:
    """Fake Anthropic Messages API; returns a pre-canned response."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.create_calls = 0

    async def create(self, **_kwargs: Any) -> Any:
        self.create_calls += 1
        return self._response


class _StubStream:
    """Async context manager mimicking ``client.messages.stream()``."""

    def __init__(self, deltas: list[str], final: Any) -> None:
        self._deltas = deltas
        self._final = final

    async def __aenter__(self) -> "_StubStream":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    @property
    def text_stream(self) -> Any:
        async def _gen() -> Any:
            for delta in self._deltas:
                yield delta

        return _gen()

    async def get_final_message(self) -> Any:
        return self._final


class _StubStreamMessages:
    def __init__(self, deltas: list[str], final: Any) -> None:
        self._deltas = deltas
        self._final = final

    def stream(self, **_kwargs: Any) -> _StubStream:
        return _StubStream(self._deltas, self._final)


def _make_response(text: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model="claude-haiku-4-5-20251001",
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=7,
            output_tokens=3,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


@pytest.mark.asyncio
async def test_generate_creates_generation_when_span_bound() -> None:
    anthropic_response = _make_response("hello")
    fake_client = SimpleNamespace(messages=_StubMessages(anthropic_response))

    fake_gen = MagicMock()
    fake_gen.end = MagicMock()
    tracer = MagicMock()
    tracer.start_generation = MagicMock(return_value=fake_gen)

    client = ClaudeClient(client=fake_client, tracer=tracer)

    span = SimpleNamespace(trace_id="bid-42", end=lambda **_: None)
    async with span_context(span):
        resp = await client.generate(
            model="claude-haiku-4-5-20251001",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            node_name="extract_requirements",
        )

    assert resp.text == "hello"
    tracer.start_generation.assert_called_once()
    start_kwargs = tracer.start_generation.call_args.kwargs
    assert start_kwargs["trace_id"] == "bid-42"
    assert start_kwargs["parent_span"] is span
    assert start_kwargs["name"] == "extract_requirements"
    assert start_kwargs["model"] == "claude-haiku-4-5-20251001"

    fake_gen.end.assert_called_once()
    end_kwargs = fake_gen.end.call_args.kwargs
    assert end_kwargs["output"] == "hello"
    assert end_kwargs["usage"] == {
        "input_tokens": 7,
        "output_tokens": 3,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


@pytest.mark.asyncio
async def test_generate_stream_captures_aggregate_on_stream_close() -> None:
    final_msg = _make_response("hello world")
    fake_client = SimpleNamespace(
        messages=_StubStreamMessages(deltas=["hel", "lo ", "world"], final=final_msg)
    )

    fake_gen = MagicMock()
    fake_gen.end = MagicMock()
    tracer = MagicMock()
    tracer.start_generation = MagicMock(return_value=fake_gen)

    client = ClaudeClient(client=fake_client, tracer=tracer)

    collected: list[str] = []

    async def on_token(delta: str) -> None:
        collected.append(delta)

    span = SimpleNamespace(trace_id="bid-7", end=lambda **_: None)
    async with span_context(span):
        resp = await client.generate_stream(
            model="claude-sonnet-4-6",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            on_token=on_token,
            node_name="synthesize_draft",
        )

    assert collected == ["hel", "lo ", "world"]
    assert resp.text == "hello world"
    tracer.start_generation.assert_called_once()
    assert tracer.start_generation.call_args.kwargs["metadata"] == {"streaming": True}
    fake_gen.end.assert_called_once()
    assert fake_gen.end.call_args.kwargs["output"] == "hello world"


@pytest.mark.asyncio
async def test_generate_is_noop_when_no_span_bound() -> None:
    fake_client = SimpleNamespace(messages=_StubMessages(_make_response("x")))
    tracer = MagicMock()
    tracer.start_generation = MagicMock()

    client = ClaudeClient(client=fake_client, tracer=tracer)

    resp = await client.generate(
        model="claude-haiku-4-5-20251001",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        node_name="extract_requirements",
    )

    assert resp.text == "x"
    tracer.start_generation.assert_not_called()


@pytest.mark.asyncio
async def test_generate_closes_generation_on_error() -> None:
    class _ExplodingMessages:
        async def create(self, **_kwargs: Any) -> Any:
            raise RuntimeError("anthropic down")

    fake_client = SimpleNamespace(messages=_ExplodingMessages())
    fake_gen = MagicMock()
    tracer = MagicMock()
    tracer.start_generation = MagicMock(return_value=fake_gen)

    client = ClaudeClient(client=fake_client, tracer=tracer)

    span = _NoopSpan()
    span.trace_id = "bid-1"  # type: ignore[misc] — _NoopSpan has class-level default
    async with span_context(span):
        with pytest.raises(RuntimeError):
            await client.generate(
                model="claude-haiku-4-5-20251001",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                node_name="extract_requirements",
            )

    fake_gen.end.assert_called_once()
    assert fake_gen.end.call_args.kwargs["metadata"] == {"status": "error"}
