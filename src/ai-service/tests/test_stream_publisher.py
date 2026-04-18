"""Phase 2.5 TokenPublisher unit tests — shape + batching + lifecycle + context binding."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from agents.stream_publisher import (
    BID_EVENTS_CHANNEL_PREFIX,
    TokenPublisher,
    get_current_publisher,
    stream_context,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.closed = False

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def aclose(self) -> None:
        self.closed = True


def _decode(fake: _FakeRedis) -> list[dict[str, Any]]:
    return [json.loads(msg) for _, msg in fake.published]


async def test_publish_shape_matches_contract() -> None:
    """Payload shape must match the frontend + gateway contract exactly."""
    fake = _FakeRedis()
    pub = TokenPublisher(
        bid_id="b1", agent="ba", attempt=1, client=fake, threshold_chars=5
    )
    await pub.set_node("synthesize_draft")
    await pub.push("hello")  # 5 chars -> immediate flush
    assert len(fake.published) == 1
    channel, raw = fake.published[0]
    assert channel == f"{BID_EVENTS_CHANNEL_PREFIX}.b1"
    payload = json.loads(raw)
    assert payload == {
        "type": "agent_token",
        "agent": "ba",
        "node": "synthesize_draft",
        "attempt": 1,
        "seq": 1,
        "text_delta": "hello",
        "done": False,
    }
    await pub.aclose()


async def test_threshold_triggers_immediate_flush() -> None:
    """Accumulated >=threshold_chars must publish without waiting for the timer."""
    fake = _FakeRedis()
    pub = TokenPublisher(
        bid_id="b1", agent="sa", attempt=1, client=fake, threshold_chars=10
    )
    await pub.set_node("synthesize")
    await pub.push("short")  # 5 chars, no flush
    assert fake.published == []
    await pub.push("more text")  # 14 chars total -> flush
    assert len(fake.published) == 1
    assert _decode(fake)[0]["text_delta"] == "shortmore text"
    await pub.aclose()


async def test_interval_timer_flushes_small_buffer() -> None:
    """A short chunk under threshold must still flush once the interval elapses."""
    fake = _FakeRedis()
    pub = TokenPublisher(
        bid_id="b1",
        agent="domain",
        attempt=1,
        client=fake,
        threshold_chars=1000,
        interval_seconds=0.02,
    )
    await pub.set_node("tag")
    await pub.push("small")
    assert fake.published == []
    await asyncio.sleep(0.05)
    assert len(fake.published) == 1
    assert _decode(fake)[0]["text_delta"] == "small"
    await pub.aclose()


async def test_mark_done_flushes_and_emits_done_event() -> None:
    """mark_done must flush remaining text + publish a done=True terminator with incremented seq."""
    fake = _FakeRedis()
    pub = TokenPublisher(bid_id="b1", agent="ba", attempt=2, client=fake)
    await pub.set_node("self_critique")
    await pub.push("final ")
    await pub.mark_done()
    decoded = _decode(fake)
    assert len(decoded) == 2
    assert decoded[0]["text_delta"] == "final "
    assert decoded[0]["done"] is False
    assert decoded[0]["seq"] == 1
    assert decoded[1]["done"] is True
    assert decoded[1]["seq"] == 2
    assert decoded[1]["attempt"] == 2
    await pub.aclose()


async def test_set_node_flushes_prior_and_resets_seq() -> None:
    """Switching node must flush the previous node's buffer and restart seq numbering."""
    fake = _FakeRedis()
    pub = TokenPublisher(
        bid_id="b1",
        agent="ba",
        attempt=1,
        client=fake,
        threshold_chars=1000,
        interval_seconds=0.05,
    )
    await pub.set_node("extract_requirements")
    await pub.push("chunk1")
    await pub.set_node("synthesize_draft")  # flushes prior
    await pub.push("chunk2")
    await pub.mark_done()
    decoded = _decode(fake)
    # [0] extract/chunk1 seq=1, [1] synth/chunk2 seq=1, [2] synth done seq=2
    assert decoded[0]["node"] == "extract_requirements"
    assert decoded[0]["seq"] == 1
    assert decoded[0]["text_delta"] == "chunk1"
    assert decoded[1]["node"] == "synthesize_draft"
    assert decoded[1]["seq"] == 1
    assert decoded[1]["text_delta"] == "chunk2"
    assert decoded[2]["node"] == "synthesize_draft"
    assert decoded[2]["seq"] == 2
    assert decoded[2]["done"] is True
    await pub.aclose()


async def test_stream_context_binds_and_resets_publisher() -> None:
    """stream_context manager must expose publisher via contextvar, reset on exit."""
    fake = _FakeRedis()
    pub = TokenPublisher(bid_id="b1", agent="ba", attempt=1, client=fake)
    assert get_current_publisher() is None
    async with stream_context(pub) as bound:
        assert bound is pub
        assert get_current_publisher() is pub
    assert get_current_publisher() is None
    await pub.aclose()


async def test_publisher_swallows_redis_errors() -> None:
    """A failing Redis client must log + swallow; caller never sees the exception."""

    class _BrokenRedis:
        async def publish(self, *_args: Any, **_kwargs: Any) -> int:
            raise RuntimeError("redis down")

        async def aclose(self) -> None:
            pass

    pub = TokenPublisher(
        bid_id="b1", agent="ba", attempt=1, client=_BrokenRedis(), threshold_chars=5
    )
    await pub.set_node("synthesize_draft")
    # Must not raise.
    await pub.push("hello")
    await pub.mark_done()
    await pub.aclose()
