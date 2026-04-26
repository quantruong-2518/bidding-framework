"""S6 WBS activity — Temporal wrapper around the WBS agent.

Falls back to the Phase 2.1 deterministic 7-phase template when no LLM provider
is available or when the agent produces unparseable output. The wrapper always
returns a well-formed :class:`WBSDraft` so downstream activities never see None.
"""

from __future__ import annotations

import logging

from temporalio import activity

from agents.wbs_agent import _REFERENCE_TEMPLATE, run_wbs_agent
from config.llm import is_llm_available
from tools.langfuse_client import get_tracer, span_context as langfuse_span_context
from workflows.artifacts import WBSDraft, WBSInput, WBSItem

logger = logging.getLogger(__name__)


def _wbs_stub(payload: WBSInput) -> WBSDraft:
    """Phase 2.1 deterministic baseline — preserved as the fallback contract."""
    items: list[WBSItem] = [
        WBSItem(
            id=row["id"],
            name=row["name"],
            parent_id=None,
            effort_md=float(row["effort_md"]),
            owner_role=row["owner_role"],
            depends_on=[],
        )
        for row in _REFERENCE_TEMPLATE
    ]
    must_count = sum(
        1 for fr in payload.ba_draft.functional_requirements if fr.priority == "MUST"
    )
    for it in items:
        if it.id == "WBS-300":
            it.effort_md = round(it.effort_md + max(0, must_count - 3) * 8.0, 1)
    total = round(sum(it.effort_md for it in items), 1)
    timeline_weeks = max(4, int(round(total / 20.0)))
    return WBSDraft(
        bid_id=payload.bid_id,
        items=items,
        total_effort_md=total,
        timeline_weeks=timeline_weeks,
        critical_path=[
            it.id for it in items if it.id in {"WBS-200", "WBS-300", "WBS-500"}
        ],
    )


@activity.defn(name="wbs_activity")
async def wbs_activity(payload: WBSInput) -> WBSDraft:
    """Generate the Work Breakdown Structure + effort + timeline."""
    if not is_llm_available():
        activity.logger.info("wbs.fallback_to_stub bid_id=%s", payload.bid_id)
        return _wbs_stub(payload)

    activity.logger.info(
        "wbs.start bid_id=%s must_count=%d hld=%s",
        payload.bid_id,
        sum(
            1 for fr in payload.ba_draft.functional_requirements if fr.priority == "MUST"
        ),
        "yes" if payload.hld is not None else "no",
    )
    activity.heartbeat("wbs_started")

    tracer = get_tracer()
    span = tracer.start_span(
        trace_id=str(payload.bid_id),
        name="wbs",
        metadata={"attempt": activity.info().attempt, "tier": "small"},
    )
    try:
        async with langfuse_span_context(span):
            draft = await run_wbs_agent(payload)
    except Exception as exc:  # noqa: BLE001 — any agent failure → stub fallback
        activity.logger.warning(
            "wbs.agent_failed_using_stub bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        draft = _wbs_stub(payload)
    finally:
        span.end()
        await tracer.aclose()

    activity.heartbeat("wbs_completed")
    activity.logger.info(
        "wbs.done bid_id=%s items=%d total_md=%.1f weeks=%d cost_usd=%.6f",
        payload.bid_id,
        len(draft.items),
        draft.total_effort_md,
        draft.timeline_weeks,
        draft.llm_cost_usd or 0.0,
    )
    return draft
