"""S6 WBS + Estimation activity (Phase 2.1 stub)."""

from __future__ import annotations

import logging

from temporalio import activity

from workflows.artifacts import WBSDraft, WBSInput, WBSItem

logger = logging.getLogger(__name__)

_DEFAULT_PHASES: tuple[tuple[str, str, float, str], ...] = (
    ("WBS-000", "Project initiation + governance setup", 10.0, "pm"),
    ("WBS-100", "Discovery + requirements firm-up", 20.0, "ba"),
    ("WBS-200", "Solution design + architecture spikes", 25.0, "sa"),
    ("WBS-300", "Core build — MVP scope", 80.0, "pm"),
    ("WBS-400", "Integration + data migration", 30.0, "sa"),
    ("WBS-500", "Test (SIT + UAT)", 25.0, "qc"),
    ("WBS-600", "Cutover + hypercare", 15.0, "pm"),
)


@activity.defn(name="wbs_activity")
async def wbs_activity(payload: WBSInput) -> WBSDraft:
    """Generate a WBS skeleton + rough effort totals."""
    activity.logger.info("wbs.start bid_id=%s", payload.bid_id)

    items: list[WBSItem] = []
    for item_id, name, effort_md, owner in _DEFAULT_PHASES:
        items.append(
            WBSItem(
                id=item_id,
                name=name,
                parent_id=None,
                effort_md=effort_md,
                owner_role=owner,
                depends_on=[],
            )
        )

    # Bias effort when BA flags many MUST functional requirements.
    must_count = sum(1 for fr in payload.ba_draft.functional_requirements if fr.priority == "MUST")
    for it in items:
        if it.id == "WBS-300":
            it.effort_md = round(it.effort_md + max(0, must_count - 3) * 8.0, 1)

    total = round(sum(it.effort_md for it in items), 1)
    # 20 MD ≈ 1 calendar week for a 5-person pod (rough, Phase 2.1 stub).
    timeline_weeks = max(4, int(round(total / 20.0)))

    draft = WBSDraft(
        bid_id=payload.bid_id,
        items=items,
        total_effort_md=total,
        timeline_weeks=timeline_weeks,
        critical_path=[it.id for it in items if it.id in {"WBS-200", "WBS-300", "WBS-500"}],
    )
    activity.logger.info(
        "wbs.done bid_id=%s total_md=%.1f weeks=%d",
        payload.bid_id,
        total,
        timeline_weeks,
    )
    return draft
