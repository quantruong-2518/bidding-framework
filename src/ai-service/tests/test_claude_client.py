"""Unit tests for ClaudeClient — prompt caching wiring + usage extraction."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest

from tools.claude_client import HAIKU, SONNET, ClaudeClient, ClaudeResponse


def _fake_response(text: str = "ok", model: str = HAIKU) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=12,
            output_tokens=34,
            cache_creation_input_tokens=100,
            cache_read_input_tokens=200,
        ),
    )


def _make_client(response: SimpleNamespace) -> tuple[ClaudeClient, AsyncMock]:
    inner = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))
    return ClaudeClient(client=inner), inner.messages.create


@pytest.mark.asyncio
async def test_generate_enables_cache_control_on_system_by_default() -> None:
    """cache_system=True wraps the system prompt in the Anthropic ephemeral cache block."""
    client, create_mock = _make_client(_fake_response())

    resp = await client.generate(
        model=HAIKU,
        system="static system prompt",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert isinstance(resp, ClaudeResponse)
    kwargs = create_mock.await_args.kwargs
    system_payload = kwargs["system"]
    assert isinstance(system_payload, list)
    assert system_payload[0]["type"] == "text"
    assert system_payload[0]["text"] == "static system prompt"
    assert system_payload[0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["model"] == HAIKU
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_generate_cache_disabled_sends_plain_system_string() -> None:
    """cache_system=False should omit cache_control entirely."""
    client, create_mock = _make_client(_fake_response(model=SONNET))

    await client.generate(
        model=SONNET,
        system="plain",
        messages=[{"role": "user", "content": "hi"}],
        cache_system=False,
    )

    kwargs = create_mock.await_args.kwargs
    assert kwargs["system"] == "plain"


@pytest.mark.asyncio
async def test_generate_captures_usage_tokens() -> None:
    """ClaudeResponse surfaces input/output/cache_read/cache_creation counts."""
    client, _ = _make_client(_fake_response(text="answer"))

    resp = await client.generate(
        model=HAIKU,
        system="sys",
        messages=[{"role": "user", "content": "q"}],
    )

    assert resp.text == "answer"
    assert resp.stop_reason == "end_turn"
    assert resp.usage == {
        "input_tokens": 12,
        "output_tokens": 34,
        "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 200,
    }


class _FakeStream:
    def __init__(self, deltas: list[str], final_response: SimpleNamespace) -> None:
        self._deltas = deltas
        self._final = final_response

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    @property
    def text_stream(self) -> "AsyncIterator[str]":  # noqa: F821
        async def _gen() -> "AsyncIterator[str]":  # noqa: F821
            for delta in self._deltas:
                yield delta

        return _gen()

    async def get_final_message(self) -> SimpleNamespace:
        return self._final


@pytest.mark.asyncio
async def test_generate_stream_forwards_deltas_and_returns_final() -> None:
    """generate_stream must call on_token per delta + return the final ClaudeResponse."""
    deltas = ["Hello ", "world", "!"]
    final = _fake_response(text="Hello world!", model=SONNET)
    stream_obj = _FakeStream(deltas, final)

    def _stream_factory(**_kwargs: Any) -> _FakeStream:
        return stream_obj

    inner = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(),
            stream=_stream_factory,
        )
    )
    client = ClaudeClient(client=inner)

    collected: list[str] = []

    async def _on_token(text: str) -> None:
        collected.append(text)

    resp = await client.generate_stream(
        model=SONNET,
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        on_token=_on_token,
    )

    assert collected == deltas
    assert resp.text == "Hello world!"
    assert resp.stop_reason == "end_turn"
    assert resp.usage["output_tokens"] == 34


@pytest.mark.asyncio
async def test_generate_stream_without_callback_still_drains_and_returns() -> None:
    """on_token=None must still iterate the stream (otherwise Anthropic SDK stalls)."""
    stream_obj = _FakeStream(["a", "b"], _fake_response(text="ab"))
    inner = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(),
            stream=lambda **_kwargs: stream_obj,
        )
    )
    client = ClaudeClient(client=inner)
    resp = await client.generate_stream(
        model=HAIKU,
        system="sys",
        messages=[{"role": "user", "content": "q"}],
    )
    assert resp.text == "ab"


@pytest.mark.asyncio
async def test_generate_stream_swallows_on_token_errors() -> None:
    """A failing on_token callback must log + swallow; streaming continues."""
    stream_obj = _FakeStream(["x", "y", "z"], _fake_response(text="xyz"))
    inner = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(),
            stream=lambda **_kwargs: stream_obj,
        )
    )
    client = ClaudeClient(client=inner)

    async def _bad_token(_text: str) -> None:
        raise RuntimeError("publisher down")

    resp = await client.generate_stream(
        model=HAIKU,
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        on_token=_bad_token,
    )
    assert resp.text == "xyz"


@pytest.mark.asyncio
async def test_generate_concatenates_multiple_text_blocks() -> None:
    """Multi-block text responses concatenate in order; non-text blocks are skipped."""
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="part1 "),
            SimpleNamespace(type="thinking", thinking="ignored"),
            SimpleNamespace(type="text", text="part2"),
        ],
        model=HAIKU,
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    client, _ = _make_client(response)
    resp = await client.generate(
        model=HAIKU,
        system="s",
        messages=[{"role": "user", "content": "q"}],
    )
    assert resp.text == "part1 part2"
