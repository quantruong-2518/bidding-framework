"""Phase 2.5 state_transition_activity — shape + best-effort failure handling."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from activities.state_transition import (
    BID_EVENTS_CHANNEL_PREFIX,
    NotifyStateTransitionInput,
    state_transition_activity,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def aclose(self) -> None:
        pass


class _BrokenRedis:
    async def publish(self, *_args: Any, **_kwargs: Any) -> int:
        raise RuntimeError("redis outage")

    async def aclose(self) -> None:
        pass


async def test_state_transition_publishes_contract_payload() -> None:
    """Payload shape must match the frontend + EventsGateway contract exactly."""
    fake = _FakeRedis()
    payload = NotifyStateTransitionInput(
        bid_id="bid-123",
        state="S4_DONE",
        profile="M",
        artifact_keys=["convergence"],
        occurred_at=datetime(2026, 4, 18, 12, 34, 56, tzinfo=timezone.utc),
    )

    with patch(
        "activities.state_transition.aioredis.from_url", return_value=fake
    ):
        receipt = await state_transition_activity(payload)

    assert receipt.published is True
    assert receipt.channel == f"{BID_EVENTS_CHANNEL_PREFIX}.bid-123"
    assert receipt.error is None

    assert len(fake.published) == 1
    channel, raw = fake.published[0]
    assert channel == f"{BID_EVENTS_CHANNEL_PREFIX}.bid-123"
    assert json.loads(raw) == {
        "type": "state_completed",
        "state": "S4_DONE",
        "profile": "M",
        "artifact_keys": ["convergence"],
        "occurred_at": "2026-04-18T12:34:56+00:00",
    }


async def test_state_transition_swallows_redis_failure() -> None:
    """Redis outage must not raise — receipt reports published=False with the error message."""
    payload = NotifyStateTransitionInput(
        bid_id="bid-456",
        state="S9_BLOCKED",
        profile="L",
        artifact_keys=["reviews"],
        occurred_at=datetime.now(timezone.utc),
    )

    with patch(
        "activities.state_transition.aioredis.from_url", return_value=_BrokenRedis()
    ):
        receipt = await state_transition_activity(payload)

    assert receipt.published is False
    assert "redis outage" in (receipt.error or "")
    assert receipt.channel == f"{BID_EVENTS_CHANNEL_PREFIX}.bid-456"


async def test_state_transition_handles_empty_artifact_keys() -> None:
    """S1_NO_BID terminal emits no artifact keys; payload must still publish cleanly."""
    fake = _FakeRedis()
    payload = NotifyStateTransitionInput(
        bid_id="bid-no-bid",
        state="S1_NO_BID",
        profile="S",
        artifact_keys=[],
        occurred_at=datetime(2026, 4, 18, 10, 0, 0, tzinfo=timezone.utc),
    )

    with patch(
        "activities.state_transition.aioredis.from_url", return_value=fake
    ):
        receipt = await state_transition_activity(payload)

    assert receipt.published is True
    assert len(fake.published) == 1
    msg = json.loads(fake.published[0][1])
    assert msg["state"] == "S1_NO_BID"
    assert msg["artifact_keys"] == []
    assert msg["profile"] == "S"
