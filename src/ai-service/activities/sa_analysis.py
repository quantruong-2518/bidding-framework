"""S3b Solution Architecture activity — Temporal wrapper around the SA LangGraph agent.

Falls back to the deterministic stub when ANTHROPIC_API_KEY is not set so the
workflow stays runnable in deterministic-first mode until the key is wired.
"""

from __future__ import annotations

import logging

from temporalio import activity

from agents.sa_agent import run_sa_agent
from config.claude import get_claude_settings
from workflows.artifacts import SolutionArchitectureDraft, StreamInput

logger = logging.getLogger(__name__)


@activity.defn(name="sa_analysis_activity")
async def sa_analysis_activity(req: StreamInput) -> SolutionArchitectureDraft:
    """Run the SA agent; heartbeat so long LLM calls don't trip activity timeouts."""
    if not get_claude_settings().api_key:
        from activities.stream_stubs import sa_analysis_stub_activity

        activity.logger.info("sa_analysis.fallback_to_stub bid_id=%s", req.bid_id)
        return await sa_analysis_stub_activity(req)

    activity.logger.info(
        "sa_analysis.start bid_id=%s reqs=%d constraints=%d",
        req.bid_id,
        len(req.requirements),
        len(req.constraints),
    )
    activity.heartbeat("sa_agent_started")

    draft = await run_sa_agent(req)

    activity.heartbeat("sa_agent_completed")
    activity.logger.info(
        "sa_analysis.done bid_id=%s stack=%d patterns=%d confidence=%.2f",
        req.bid_id,
        len(draft.tech_stack),
        len(draft.architecture_patterns),
        draft.confidence,
    )
    return draft
