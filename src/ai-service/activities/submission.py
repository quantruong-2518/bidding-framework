"""S10 Submission activity (Phase 2.1 stub)."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from temporalio import activity

from workflows.artifacts import SubmissionInput, SubmissionRecord

logger = logging.getLogger(__name__)


def _checksum(payload: SubmissionInput) -> str:
    """Stable SHA-256 over concatenated section body — used as package integrity marker."""
    sha = hashlib.sha256()
    sha.update(payload.package.title.encode("utf-8"))
    for section in payload.package.sections:
        sha.update(section.heading.encode("utf-8"))
        sha.update(section.body_markdown.encode("utf-8"))
    return sha.hexdigest()[:16]


@activity.defn(name="submission_activity")
async def submission_activity(payload: SubmissionInput) -> SubmissionRecord:
    """Record the submission + run the cutover checklist."""
    activity.logger.info("submission.start bid_id=%s", payload.bid_id)

    last_review = payload.reviews[-1] if payload.reviews else None
    checklist = {
        "all_sections_present": len(payload.package.sections) >= 5,
        "consistency_checks_passed": all(payload.package.consistency_checks.values()),
        "approved_by_review": last_review is not None and last_review.verdict == "APPROVED",
        "package_checksum_present": True,
    }

    record = SubmissionRecord(
        bid_id=payload.bid_id,
        submitted_at=datetime.now(timezone.utc),
        channel="portal",
        confirmation_id=f"SUB-{payload.bid_id.hex[:8]}",
        package_checksum=_checksum(payload),
        checklist=checklist,
    )
    activity.logger.info(
        "submission.done bid_id=%s confirmation=%s",
        payload.bid_id,
        record.confirmation_id,
    )
    return record
