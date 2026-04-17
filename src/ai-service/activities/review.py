"""S9 Review Gate activity (Phase 2.1 stub).

Phase 2.4 replaces this with a real human approval flow:
  - Multi-reviewer (per-profile gate size; see STATE_MACHINE.md §Bid Profiles).
  - Workflow signal instead of auto-decision (same pattern as S1 human gate).
  - Loop-back on `CHANGES_REQUESTED` / `REJECTED` per STATE_MACHINE.md
    §Feedback Loops: S8 (minor) / S6 (WBS) / S5 (solution) / S2 (scope).

For now the stub emits an AUTO-APPROVED record so the DAG can reach S10.
IMPORTANT: the workflow does NOT currently loop back on non-APPROVED verdicts —
it still proceeds to S10 with `submission.checklist.approved_by_review=false`.
That is acceptable for Phase 2.1 because the consistency checks always pass
for stub-generated packages, so the verdict is always APPROVED in practice.
Do not wire any real source of `CHANGES_REQUESTED` into this path before
Phase 2.4 lands the loop-back branch in `bid_workflow.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from temporalio import activity

from workflows.artifacts import ReviewInput, ReviewRecord

logger = logging.getLogger(__name__)


@activity.defn(name="review_activity")
async def review_activity(payload: ReviewInput) -> ReviewRecord:
    """Auto-approve the proposal — placeholder until Phase 2.4 wires real reviewers."""
    activity.logger.info(
        "review.start bid_id=%s sections=%d",
        payload.bid_id,
        len(payload.package.sections),
    )

    all_consistent = all(payload.package.consistency_checks.values())
    verdict = "APPROVED" if all_consistent else "CHANGES_REQUESTED"

    record = ReviewRecord(
        bid_id=payload.bid_id,
        reviewer_role="bid_manager",
        reviewer="phase-2.1-auto",
        verdict=verdict,
        comments=[],
        reviewed_at=datetime.now(timezone.utc),
    )
    activity.logger.info(
        "review.done bid_id=%s verdict=%s", payload.bid_id, verdict
    )
    return record
