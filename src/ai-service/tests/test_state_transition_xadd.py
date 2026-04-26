"""Conv-16a state-transition XADD — payload shape, monotonic seq, fault tolerance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from activities.state_transition import (
    BID_TRANSITIONS_MAXLEN,
    BID_TRANSITIONS_STREAM,
    NotifyStateTransitionInput,
    state_transition_activity,
)


class _FakeRedis:
    """Captures publish + xadd. Records full kwargs for MAXLEN assertions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.xadd_calls: list[dict[str, Any]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def xadd(
        self,
        stream: str,
        fields: dict[str, str],
        *,
        maxlen: int | None = None,
        approximate: bool | None = None,
    ) -> str:
        self.xadd_calls.append(
            {
                "stream": stream,
                "fields": dict(fields),
                "maxlen": maxlen,
                "approximate": approximate,
            }
        )
        return "0-0"

    async def aclose(self) -> None:
        pass


def _payload(**overrides: Any) -> NotifyStateTransitionInput:
    base = dict(
        bid_id="bid-aaa",
        workflow_id="wf-aaa",
        transition_seq=1,
        tenant_id="acme",
        from_state=None,
        state="S0_DONE",
        profile="M",
        artifact_keys=["bid_card"],
        occurred_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc),
        llm_cost_delta=None,
    )
    base.update(overrides)
    return NotifyStateTransitionInput(**base)  # type: ignore[arg-type]


async def test_xadd_emits_full_contract_payload() -> None:
    """Stream entry must carry every field the projection consumer reads."""
    fake = _FakeRedis()
    payload = _payload(
        transition_seq=4,
        from_state="S2_DONE",
        state="S3_DONE",
        artifact_keys=["ba_draft", "sa_draft", "domain_notes"],
        llm_cost_delta=0.012345,
    )

    with patch(
        "activities.state_transition.aioredis.from_url", return_value=fake
    ):
        receipt = await state_transition_activity(payload)

    assert receipt.streamed is True
    assert receipt.stream == BID_TRANSITIONS_STREAM
    assert receipt.stream_error is None
    assert len(fake.xadd_calls) == 1
    call = fake.xadd_calls[0]
    assert call["stream"] == BID_TRANSITIONS_STREAM
    assert call["maxlen"] == BID_TRANSITIONS_MAXLEN
    assert call["approximate"] is True
    fields = call["fields"]
    assert fields["bid_id"] == "bid-aaa"
    assert fields["workflow_id"] == "wf-aaa"
    assert fields["transition_seq"] == "4"
    assert fields["tenant_id"] == "acme"
    assert fields["from_state"] == "S2_DONE"
    assert fields["to_state"] == "S3_DONE"
    assert fields["profile"] == "M"
    assert json.loads(fields["artifact_keys"]) == [
        "ba_draft",
        "sa_draft",
        "domain_notes",
    ]
    assert fields["occurred_at"] == "2026-04-26T12:00:00+00:00"
    assert fields["llm_cost_delta"] == "0.012345"


async def test_xadd_serialises_monotonic_seq_and_null_from_state() -> None:
    """First transition (S0_DONE) sends from_state="" and seq=1."""
    fake = _FakeRedis()
    with patch(
        "activities.state_transition.aioredis.from_url", return_value=fake
    ):
        await state_transition_activity(_payload(transition_seq=1, from_state=None))

    assert fake.xadd_calls[0]["fields"]["from_state"] == ""
    assert fake.xadd_calls[0]["fields"]["transition_seq"] == "1"


async def test_xadd_failure_does_not_block_publish() -> None:
    """XADD failure must be swallowed — pub/sub still fires; receipt records both."""

    class _PublishOkXaddFail(_FakeRedis):
        async def xadd(self, *_args: Any, **_kwargs: Any) -> str:
            raise RuntimeError("stream MAXLEN reject")

    broken = _PublishOkXaddFail()
    with patch(
        "activities.state_transition.aioredis.from_url", return_value=broken
    ):
        receipt = await state_transition_activity(_payload())

    assert receipt.published is True
    assert receipt.streamed is False
    assert "MAXLEN" in (receipt.stream_error or "")


async def test_publish_failure_does_not_block_xadd() -> None:
    """Pub/sub outage must not stop the durable stream entry from being written."""

    class _PublishFailXaddOk(_FakeRedis):
        async def publish(self, *_args: Any, **_kwargs: Any) -> int:
            raise RuntimeError("pub/sub down")

    redis = _PublishFailXaddOk()
    with patch(
        "activities.state_transition.aioredis.from_url", return_value=redis
    ):
        receipt = await state_transition_activity(_payload())

    assert receipt.published is False
    assert receipt.streamed is True
    assert "down" in (receipt.error or "")


async def test_xadd_handles_optional_cost_as_empty_string() -> None:
    """``llm_cost_delta=None`` must serialise as an empty string (not the literal "None")."""
    fake = _FakeRedis()
    with patch(
        "activities.state_transition.aioredis.from_url", return_value=fake
    ):
        await state_transition_activity(_payload(llm_cost_delta=None))

    assert fake.xadd_calls[0]["fields"]["llm_cost_delta"] == ""


@pytest.mark.parametrize(
    "to_state,profile,keys",
    [
        ("S1_NO_BID", "S", []),
        ("S9_BLOCKED", "L", ["reviews"]),
        ("S11_DONE", "M", ["retrospective"]),
    ],
)
async def test_xadd_terminal_states_serialise_cleanly(
    to_state: str, profile: str, keys: list[str]
) -> None:
    """Terminal-state events must still produce well-formed stream entries."""
    fake = _FakeRedis()
    payload = _payload(state=to_state, profile=profile, artifact_keys=keys)
    with patch(
        "activities.state_transition.aioredis.from_url", return_value=fake
    ):
        receipt = await state_transition_activity(payload)

    assert receipt.streamed is True
    fields = fake.xadd_calls[0]["fields"]
    assert fields["to_state"] == to_state
    assert fields["profile"] == profile
    assert json.loads(fields["artifact_keys"]) == keys
