"""S9 approval-needed notification activity (Phase 2.4).

Publishes a `bid.event` payload (`type: "approval_needed"`) to the Redis
pub/sub channel the NestJS `EventsGateway` listens on. The frontend toast +
dashboard badge consume it via the existing WebSocket fanout.

This activity is **best-effort** — Redis outages must not block workflow
progress. Exceptions are logged and swallowed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Literal

import redis.asyncio as aioredis
from pydantic import BaseModel, Field
from temporalio import activity

logger = logging.getLogger(__name__)

BID_EVENTS_CHANNEL_PREFIX = "bid.events.channel"


class NotifyApprovalInput(BaseModel):
    """Input payload for `notify_approval_needed_activity`."""

    bid_id: str
    workflow_id: str
    state: Literal["S9"] = "S9"
    profile: str
    round: int = Field(ge=1)
    reviewer_index: int = Field(ge=0)
    reviewer_count: int = Field(ge=1)


class NotifyReceipt(BaseModel):
    """Return payload — always reports success even on Redis failure.

    The workflow never branches on this; it's purely for activity traces.
    """

    published: bool
    channel: str
    error: str | None = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@activity.defn(name="notify_approval_needed_activity")
async def notify_approval_needed_activity(
    payload: NotifyApprovalInput,
) -> NotifyReceipt:
    """Publish an approval_needed bid.event. Best-effort; never raises."""
    channel = f"{BID_EVENTS_CHANNEL_PREFIX}.{payload.bid_id}"
    message = {
        "type": "approval_needed",
        "state": payload.state,
        "workflow_id": payload.workflow_id,
        "round": payload.round,
        "reviewer_index": payload.reviewer_index,
        "reviewer_count": payload.reviewer_count,
        "profile": payload.profile,
    }
    activity.logger.info(
        "notify.approval_needed bid=%s wf=%s round=%d reviewer=%d/%d",
        payload.bid_id,
        payload.workflow_id,
        payload.round,
        payload.reviewer_index + 1,
        payload.reviewer_count,
    )
    client = None
    try:
        client = aioredis.from_url(_redis_url(), decode_responses=True)
        await client.publish(channel, json.dumps(message))
        return NotifyReceipt(published=True, channel=channel)
    except Exception as exc:  # noqa: BLE001 — notification never blocks the workflow
        activity.logger.warning(
            "notify.approval_needed.failed bid=%s err=%s", payload.bid_id, exc
        )
        return NotifyReceipt(published=False, channel=channel, error=str(exc))
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
