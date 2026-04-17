"""S2 Scoping activity — decompose RFP requirements and assign to parallel streams."""

from __future__ import annotations

import logging
import re

from temporalio import activity

from workflows.models import (
    BidCard,
    BidProfile,
    RequirementAtom,
    RequirementCategory,
    ScopingResult,
)

logger = logging.getLogger(__name__)

_CATEGORY_KEYWORDS: dict[RequirementCategory, tuple[str, ...]] = {
    "compliance": (
        "hipaa",
        "pci",
        "gdpr",
        "iso",
        "sox",
        "audit",
        "regulat",
        "complianc",
        "privacy",
    ),
    "nfr": (
        "latency",
        "throughput",
        "availability",
        "uptime",
        "performance",
        "scalab",
        "sla",
        "rto",
        "rpo",
        "security",
        "encrypt",
    ),
    "technical": (
        "api",
        "microservice",
        "database",
        "queue",
        "kafka",
        "cloud",
        "kubernetes",
        "docker",
        "architecture",
        "integration",
    ),
    "timeline": (
        "deadline",
        "milestone",
        "go-live",
        "go live",
        "launch",
        "by q",
        "by quarter",
        "within",
        "weeks",
        "months",
    ),
    "functional": (
        "shall",
        "must",
        "should",
        "user ",
        "users ",
        "allow",
        "enable",
        "support",
        "provide",
        "feature",
    ),
}

_TEAM_TABLE: dict[BidProfile, dict[str, int]] = {
    "S": {"bid_manager": 1, "ba": 1, "sa": 1},
    "M": {"bid_manager": 1, "ba": 1, "sa": 1, "pm": 1, "qc": 1},
    "L": {"bid_manager": 1, "ba": 2, "sa": 2, "pm": 1, "qc": 1, "domain_expert": 1},
    "XL": {
        "bid_manager": 1,
        "ba": 3,
        "sa": 2,
        "pm": 2,
        "qc": 2,
        "domain_expert": 2,
        "solution_lead": 1,
    },
}

_STREAM_ROUTES: dict[RequirementCategory, str] = {
    "functional": "S3a",
    "nfr": "S3b",
    "technical": "S3b",
    "compliance": "S3c",
    "timeline": "S3a",
    "unclear": "S3a",
}


def _classify(text: str) -> RequirementCategory:
    lower = text.lower()
    for category, needles in _CATEGORY_KEYWORDS.items():
        for needle in needles:
            if needle in lower:
                return category
    if len(lower.split()) < 4:
        return "unclear"
    return "functional"


def _clean_id(prefix: str, idx: int) -> str:
    return f"{prefix}-{idx:03d}"


def _assign_streams(
    atoms: list[RequirementAtom], profile: BidProfile
) -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}
    for atom in atoms:
        target = _STREAM_ROUTES[atom.category]
        if target == "S3c" and profile == "S":
            target = "S3a"  # domain mining skipped for Bid S
        assignments.setdefault(target, []).append(atom.id)
    return assignments


def _section_for(text: str) -> str | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\s", text)
    return match.group(1) if match else None


@activity.defn(name="scoping_activity")
async def scoping_activity(bid_card: BidCard) -> ScopingResult:
    """Decompose requirements into categorised atoms + stream routing + team suggestion."""
    activity.logger.info(
        "scoping.start bid_id=%s reqs=%d", bid_card.bid_id, len(bid_card.requirements_raw)
    )

    atoms: list[RequirementAtom] = []
    for idx, raw in enumerate(bid_card.requirements_raw, start=1):
        text = raw.strip()
        if not text:
            continue
        atoms.append(
            RequirementAtom(
                id=_clean_id("REQ", idx),
                text=text,
                category=_classify(text),
                source_section=_section_for(text),
            )
        )

    profile = bid_card.estimated_profile
    result = ScopingResult(
        requirement_map=atoms,
        stream_assignments=_assign_streams(atoms, profile),
        team_suggestion=_TEAM_TABLE[profile],
    )
    activity.logger.info(
        "scoping.done bid_id=%s atoms=%d streams=%s",
        bid_card.bid_id,
        len(atoms),
        list(result.stream_assignments.keys()),
    )
    return result
