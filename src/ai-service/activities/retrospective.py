"""S11 Retrospective activity (Phase 2.1 stub)."""

from __future__ import annotations

import logging

from temporalio import activity

from workflows.artifacts import Lesson, RetrospectiveDraft, RetrospectiveInput

logger = logging.getLogger(__name__)


@activity.defn(name="retrospective_activity")
async def retrospective_activity(payload: RetrospectiveInput) -> RetrospectiveDraft:
    """Capture default lessons + KB update queue — real analysis arrives in Phase 3.4."""
    activity.logger.info("retrospective.start bid_id=%s", payload.bid_id)

    checklist = payload.submission.checklist
    lessons = [
        Lesson(
            title="Cross-stream readiness baseline",
            category="process",
            detail="Record readiness at S4 convergence to benchmark future bids.",
        ),
        Lesson(
            title="Effort vs estimate delta",
            category="estimation",
            detail="After delivery, compare WBS estimates to actuals to tune the model.",
        ),
    ]
    if not checklist.get("consistency_checks_passed", False):
        lessons.append(
            Lesson(
                title="Assembly consistency gaps",
                category="process",
                detail="Submission passed with consistency warnings — tighten S8 checks.",
            )
        )

    kb_updates = [
        f"retrospective/{payload.bid_id}.md",  # placeholder path; real vault wiring in 2.7
    ]

    draft = RetrospectiveDraft(
        bid_id=payload.bid_id,
        outcome="PENDING",
        lessons=lessons,
        kb_updates=kb_updates,
    )
    activity.logger.info(
        "retrospective.done bid_id=%s lessons=%d", payload.bid_id, len(lessons)
    )
    return draft
