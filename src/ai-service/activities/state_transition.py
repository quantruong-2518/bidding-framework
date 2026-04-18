"""Phase 2.5 state_completed notification activity.

Publishes a ``state_completed`` bid.event to the Redis pub/sub channel after
each workflow phase completes (post-vault-snapshot, so subscribers re-fetching
artifacts observe read-your-writes on the kb-vault workspace).

Best-effort — Redis outages must not block workflow progress. Exceptions are
logged via the Temporal activity logger and swallowed; the receipt reports
``published=False`` so activity traces still capture the failure.

Published payload shape (on ``bid.events.channel.{bid_id}``)::

    {
        "type": "state_completed",
        "state": "S4_DONE",          # phase identifier; free-form string
        "profile": "S" | "M" | "L" | "XL",
        "artifact_keys": ["convergence"],   # BidState fields written this phase
        "occurred_at": "2026-04-18T12:34:56+00:00",
    }
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


class NotifyStateTransitionInput(BaseModel):
    """Input payload for :func:`state_transition_activity`."""

    bid_id: str
    state: str
    profile: BidProfile
    artifact_keys: list[str] = Field(default_factory=list)
    occurred_at: datetime


class NotifyStateTransitionReceipt(BaseModel):
    """Return payload — always reports, even on Redis failure, for activity traces."""

    published: bool
    channel: str
    error: str | None = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@activity.defn(name="state_transition_activity")
async def state_transition_activity(
    payload: NotifyStateTransitionInput,
) -> NotifyStateTransitionReceipt:
    """Publish a ``state_completed`` bid.event. Best-effort; never raises."""
    channel = f"{BID_EVENTS_CHANNEL_PREFIX}.{payload.bid_id}"
    message = {
        "type": "state_completed",
        "state": payload.state,
        "profile": payload.profile,
        "artifact_keys": list(payload.artifact_keys),
        "occurred_at": payload.occurred_at.isoformat(),
    }
    activity.logger.info(
        "state_transition.notify bid=%s state=%s keys=%d",
        payload.bid_id,
        payload.state,
        len(payload.artifact_keys),
    )
    client = None
    try:
        client = aioredis.from_url(_redis_url(), decode_responses=True)
        await client.publish(channel, json.dumps(message))
        return NotifyStateTransitionReceipt(published=True, channel=channel)
    except Exception as exc:  # noqa: BLE001 — notification never blocks the workflow
        activity.logger.warning(
            "state_transition.notify.failed bid=%s err=%s", payload.bid_id, exc
        )
        return NotifyStateTransitionReceipt(
            published=False, channel=channel, error=str(exc)
        )
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
