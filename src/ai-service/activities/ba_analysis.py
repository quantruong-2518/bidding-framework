"""S3a Business Analysis activity — Temporal wrapper around the BA LangGraph agent.

Falls back to the deterministic stub when ANTHROPIC_API_KEY is not set so the
workflow + worker remain runnable in deterministic-first mode (Phase 2.2 built
with key-less delivery in mind; stub path is the ``ANTHROPIC_API_KEY`` gate).
"""

from __future__ import annotations

import logging

from temporalio import activity

from agents.ba_agent import run_ba_agent
from agents.models import BusinessRequirementsDraft
from agents.stream_publisher import TokenPublisher, stream_context
from config.claude import get_claude_settings
from tools.langfuse_client import get_tracer, span_context as langfuse_span_context
from workflows.artifacts import StreamInput

logger = logging.getLogger(__name__)


@activity.defn(name="ba_analysis_activity")
async def ba_analysis_activity(req: StreamInput) -> BusinessRequirementsDraft:
    """Run the BA agent; heartbeat so long LLM calls don't trip activity timeouts."""
    if not get_claude_settings().api_key:
        from activities.stream_stubs import ba_analysis_stub_activity

        activity.logger.info("ba_analysis.fallback_to_stub bid_id=%s", req.bid_id)
        return await ba_analysis_stub_activity(req)

    activity.logger.info(
        "ba_analysis.start bid_id=%s reqs=%d constraints=%d",
        req.bid_id,
        len(req.requirements),
        len(req.constraints),
    )
    activity.heartbeat("ba_agent_started")

    # Phase 2.5 — bind a throttled Redis publisher so LLM deltas fan out to
    # the frontend AgentStreamPanel. Activity retry re-emits with a new
    # `attempt_number` so the frontend can de-dupe stale attempts.
    publisher = TokenPublisher(
        bid_id=str(req.bid_id),
        agent="ba",
        attempt=activity.info().attempt,
    )
    # Phase 3.5 — open a Langfuse span so every LLM call under the BA graph
    # is attached to `trace_id=str(bid_id)`. Noop when LANGFUSE_SECRET_KEY unset.
    tracer = get_tracer()
    span = tracer.start_span(
        trace_id=str(req.bid_id),
        name="ba_analysis",
        metadata={"attempt": activity.info().attempt, "agent": "ba"},
    )
    try:
        async with langfuse_span_context(span), stream_context(publisher):
            draft = await run_ba_agent(req)
    finally:
        await publisher.aclose()
        span.end()
        await tracer.aclose()

    activity.heartbeat("ba_agent_completed")
    activity.logger.info(
        "ba_analysis.done bid_id=%s functional=%d risks=%d confidence=%.2f",
        req.bid_id,
        len(draft.functional_requirements),
        len(draft.risks),
        draft.confidence,
    )
    return draft
