"""S4 Convergence activity (Phase 2.1 stub).

Merges S3a/b/c outputs into a unified view. Real conflict detection + readiness
scoring arrives in Phase 2.2.
"""

from __future__ import annotations

import logging

from temporalio import activity

from workflows.artifacts import ConvergenceInput, ConvergenceReport

logger = logging.getLogger(__name__)


@activity.defn(name="convergence_activity")
async def convergence_activity(payload: ConvergenceInput) -> ConvergenceReport:
    """Stub merge of BA / SA / Domain streams."""
    activity.logger.info("convergence.start bid_id=%s", payload.bid_id)

    readiness = {
        "S3a": round(payload.ba_draft.confidence, 2),
        "S3b": round(payload.sa_draft.confidence, 2),
        "S3c": round(payload.domain_notes.confidence, 2),
    }

    unified = (
        f"Unified view for bid {payload.bid_id}. "
        f"BA functional items: {len(payload.ba_draft.functional_requirements)}. "
        f"SA patterns: {len(payload.sa_draft.architecture_patterns)}. "
        f"Compliance obligations: {len(payload.domain_notes.compliance)}."
    )

    open_questions: list[str] = []
    if any(score < 0.6 for score in readiness.values()):
        open_questions.append("One or more streams below 60% confidence — consider re-running.")
    if not payload.ba_draft.success_criteria:
        open_questions.append("Success criteria not yet defined by BA stream.")

    report = ConvergenceReport(
        bid_id=payload.bid_id,
        unified_summary=unified,
        readiness=readiness,
        conflicts=[],  # Phase 2.2 detects real cross-stream conflicts.
        open_questions=open_questions,
    )
    activity.logger.info(
        "convergence.done bid_id=%s readiness=%s questions=%d",
        payload.bid_id,
        readiness,
        len(open_questions),
    )
    return report
