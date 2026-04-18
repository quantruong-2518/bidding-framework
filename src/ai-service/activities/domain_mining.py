"""S3c Domain Mining activity — Temporal wrapper around the Domain LangGraph agent.

Falls back to the deterministic stub when ANTHROPIC_API_KEY is not set so the
workflow stays runnable in deterministic-first mode until the key is wired.
"""

from __future__ import annotations

import logging

from temporalio import activity

from agents.domain_agent import run_domain_agent
from agents.stream_publisher import TokenPublisher, stream_context
from config.claude import get_claude_settings
from workflows.artifacts import DomainNotes, StreamInput

logger = logging.getLogger(__name__)


@activity.defn(name="domain_mining_activity")
async def domain_mining_activity(req: StreamInput) -> DomainNotes:
    """Run the Domain agent; heartbeat so long LLM calls don't trip activity timeouts."""
    if not get_claude_settings().api_key:
        from activities.stream_stubs import domain_mining_stub_activity

        activity.logger.info("domain_mining.fallback_to_stub bid_id=%s", req.bid_id)
        return await domain_mining_stub_activity(req)

    activity.logger.info(
        "domain_mining.start bid_id=%s industry=%s reqs=%d",
        req.bid_id,
        req.industry,
        len(req.requirements),
    )
    activity.heartbeat("domain_agent_started")

    publisher = TokenPublisher(
        bid_id=str(req.bid_id),
        agent="domain",
        attempt=activity.info().attempt,
    )
    try:
        async with stream_context(publisher):
            notes = await run_domain_agent(req)
    finally:
        await publisher.aclose()

    activity.heartbeat("domain_agent_completed")
    activity.logger.info(
        "domain_mining.done bid_id=%s compliance=%d practices=%d confidence=%.2f",
        req.bid_id,
        len(notes.compliance),
        len(notes.best_practices),
        notes.confidence,
    )
    return notes
