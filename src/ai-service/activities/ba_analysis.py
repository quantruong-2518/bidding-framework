"""S3a Business Analysis activity — Temporal wrapper around the BA LangGraph agent."""

from __future__ import annotations

import logging

from temporalio import activity

from agents.ba_agent import run_ba_agent
from agents.models import BARequirements, BusinessRequirementsDraft

logger = logging.getLogger(__name__)


@activity.defn(name="ba_analysis_activity")
async def ba_analysis_activity(req: BARequirements) -> BusinessRequirementsDraft:
    """Run the BA agent; heartbeat so long LLM calls don't trip activity timeouts."""
    activity.logger.info(
        "ba_analysis.start bid_id=%s reqs=%d constraints=%d",
        req.bid_id,
        len(req.requirements),
        len(req.constraints),
    )
    activity.heartbeat("ba_agent_started")

    draft = await run_ba_agent(req)

    activity.heartbeat("ba_agent_completed")
    activity.logger.info(
        "ba_analysis.done bid_id=%s functional=%d risks=%d confidence=%.2f",
        req.bid_id,
        len(draft.functional_requirements),
        len(draft.risks),
        draft.confidence,
    )
    return draft
