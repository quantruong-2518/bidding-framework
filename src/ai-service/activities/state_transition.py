"""Phase 2.5 / Conv-16a state-transition notification activity.

Two side-effects per transition, both best-effort:

* PUBLISH on ``bid.events.channel.{bid_id}`` — pub/sub, drives the WebSocket
  fanout for live UIs (Phase 2.5).
* XADD on ``bid.transitions`` — durable Redis Stream, consumed by the
  NestJS ``BidStateProjectionConsumer`` to maintain the CQRS read model
  (Conv-16a). XADD MAXLEN ~ 1_000_000 caps the stream at ~30 days @ 30k
  transitions/day; the `bid_state_transitions` Postgres table is the
  permanent log.

Both calls swallow exceptions. The receipt records which sinks succeeded so
activity traces stay informative when one of the two is degraded.

Published payload shape (pub/sub channel)::

    {
        "type": "state_completed",
        "state": "S4_DONE",
        "profile": "S" | "M" | "L" | "XL",
        "artifact_keys": ["convergence"],
        "occurred_at": "2026-04-18T12:34:56+00:00",
    }

Stream entry fields (``bid.transitions``)::

    bid_id, workflow_id, transition_seq, tenant_id, from_state, to_state,
    profile, artifact_keys (JSON), occurred_at, llm_cost_delta
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import redis.asyncio as aioredis
from pydantic import BaseModel, Field
from temporalio import activity

from workflows.base import BidProfile

logger = logging.getLogger(__name__)

BID_EVENTS_CHANNEL_PREFIX = "bid.events.channel"
BID_TRANSITIONS_STREAM = "bid.transitions"
BID_TRANSITIONS_MAXLEN = 1_000_000


class NotifyStateTransitionInput(BaseModel):
    """Input payload for :func:`state_transition_activity`."""

    bid_id: str
    # Conv-16a fields. Every existing test that omitted these still works
    # because all five are optional / defaulted.
    workflow_id: str = ""
    transition_seq: int = 0
    tenant_id: str = ""
    from_state: str | None = None
    state: str  # to-state (kept name for backward compat with Phase 2.5 callers)
    profile: BidProfile
    artifact_keys: list[str] = Field(default_factory=list)
    occurred_at: datetime
    llm_cost_delta: float | None = None


class NotifyStateTransitionReceipt(BaseModel):
    """Return payload — always reports, even on Redis failure, for activity traces."""

    published: bool
    channel: str
    streamed: bool = False
    stream: str = BID_TRANSITIONS_STREAM
    error: str | None = None
    stream_error: str | None = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@activity.defn(name="state_transition_activity")
async def state_transition_activity(
    payload: NotifyStateTransitionInput,
) -> NotifyStateTransitionReceipt:
    """Publish a ``state_completed`` event + append a stream entry. Best-effort."""
    channel = f"{BID_EVENTS_CHANNEL_PREFIX}.{payload.bid_id}"
    message = {
        "type": "state_completed",
        "state": payload.state,
        "profile": payload.profile,
        "artifact_keys": list(payload.artifact_keys),
        "occurred_at": payload.occurred_at.isoformat(),
    }
    activity.logger.info(
        "state_transition.notify bid=%s state=%s seq=%d keys=%d",
        payload.bid_id,
        payload.state,
        payload.transition_seq,
        len(payload.artifact_keys),
    )

    receipt = NotifyStateTransitionReceipt(published=False, channel=channel)
    client = None
    try:
        client = aioredis.from_url(_redis_url(), decode_responses=True)
        try:
            await client.publish(channel, json.dumps(message))
            receipt.published = True
        except Exception as exc:  # noqa: BLE001 — pub/sub is best-effort
            activity.logger.warning(
                "state_transition.publish.failed bid=%s err=%s", payload.bid_id, exc
            )
            receipt.error = str(exc)

        try:
            await client.xadd(
                BID_TRANSITIONS_STREAM,
                _stream_fields(payload),
                maxlen=BID_TRANSITIONS_MAXLEN,
                approximate=True,
            )
            receipt.streamed = True
        except Exception as exc:  # noqa: BLE001 — stream is best-effort
            activity.logger.warning(
                "state_transition.xadd.failed bid=%s seq=%d err=%s",
                payload.bid_id,
                payload.transition_seq,
                exc,
            )
            receipt.stream_error = str(exc)

        return receipt
    except Exception as exc:  # noqa: BLE001 — connection-time failure
        activity.logger.warning(
            "state_transition.notify.failed bid=%s err=%s", payload.bid_id, exc
        )
        receipt.error = str(exc)
        return receipt
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass


def _stream_fields(payload: NotifyStateTransitionInput) -> dict[str, str]:
    """Flatten the payload into the ``XADD`` field/value mapping."""
    return {
        "bid_id": payload.bid_id,
        "workflow_id": payload.workflow_id,
        "transition_seq": str(payload.transition_seq),
        "tenant_id": payload.tenant_id,
        "from_state": payload.from_state or "",
        "to_state": payload.state,
        "profile": payload.profile,
        "artifact_keys": json.dumps(list(payload.artifact_keys)),
        "occurred_at": payload.occurred_at.isoformat(),
        "llm_cost_delta": (
            "" if payload.llm_cost_delta is None else f"{payload.llm_cost_delta:.6f}"
        ),
    }
