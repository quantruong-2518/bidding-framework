"""S9 Review Gate — pre-human consistency check (Phase 2.4).

This activity runs BEFORE the human review signal waits; it seeds the
`state.reviews` log with an AI-derived verdict based on the proposal's
consistency checks. The real human decision is delivered via the
`human_review_decision` workflow signal and supplements/overrides this
record (see `bid_workflow.py::_run_s9_review_gate`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from temporalio import activity

from workflows.artifacts import ReviewInput, ReviewRecord

logger = logging.getLogger(__name__)


def _pre_human_review_impl(payload: ReviewInput) -> ReviewRecord:
    """Pure helper: derive the pre-human record. Kept separate for unit tests."""
    all_consistent = all(payload.package.consistency_checks.values())
    verdict = "APPROVED" if all_consistent else "CHANGES_REQUESTED"
    return ReviewRecord(
        bid_id=payload.bid_id,
        reviewer_role="bid_manager",
        reviewer="phase-2.4-pre-human",
        verdict=verdict,
        comments=[],
        reviewed_at=datetime.now(timezone.utc),
    )


@activity.defn(name="review_activity")
async def review_activity(payload: ReviewInput) -> ReviewRecord:
    """Pre-human AI review: flag inconsistencies before the human reviewer sees the package."""
    activity.logger.info(
        "review.pre_human.start bid_id=%s sections=%d",
        payload.bid_id,
        len(payload.package.sections),
    )
    record = _pre_human_review_impl(payload)
    activity.logger.info(
        "review.pre_human.done bid_id=%s verdict=%s", payload.bid_id, record.verdict
    )
    return record
