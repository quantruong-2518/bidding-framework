"""S4 Convergence activity — merge S3a/b/c outputs + heuristic cross-stream checks.

Phase 2.2 conflict detection is deliberately rule-based (regex + field presence)
rather than LLM-compare: deterministic, testable, catches the common 80%. Rules:

    R1 (API layer mismatch):
        If any BA functional requirement mentions REST / GraphQL / gRPC, the SA
        tech_stack's API-layer entry must name the same protocol — else MAJOR.
    R2 (compliance gap):
        If DomainNotes.compliance contains PCI DSS / HIPAA / GDPR, the SA must
        name at least one architecture_pattern signalling segmentation /
        encryption / audit — else MAJOR.
    R3 (NFR field presence):
        If BA.success_criteria mentions latency / uptime / availability, SA's
        nfr_targets must declare the corresponding key — else MEDIUM.

Readiness score is a weighted mix:

    readiness = 0.40 * ba.confidence + 0.35 * sa.confidence + 0.25 * domain.confidence

If readiness < 0.80 the convergence surfaces an `open_questions` entry naming
the streams below threshold; Phase 2.4 will use this to decide whether to route
back to S2 rework.
"""

from __future__ import annotations

import logging
import re

from temporalio import activity

from workflows.artifacts import (
    BusinessRequirementsDraft,
    ConvergenceInput,
    ConvergenceReport,
    DomainNotes,
    SolutionArchitectureDraft,
    StreamConflict,
)

logger = logging.getLogger(__name__)

READINESS_WEIGHTS = {"ba": 0.40, "sa": 0.35, "domain": 0.25}
READINESS_GATE = 0.80

_API_PROTOCOLS = ("REST", "GraphQL", "gRPC")
_COMPLIANCE_HOT = ("PCI DSS", "HIPAA", "GDPR")
_SECURITY_KEYWORDS = ("segmentation", "encryption", "audit", "access control", "tokenisation", "tokenization")

_NFR_TOKEN_TO_KEY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(latenc|p95|response\s*time)\b", re.IGNORECASE), "p95_latency_ms"),
    (re.compile(r"\b(uptime|availabilit)\b", re.IGNORECASE), "availability"),
    (re.compile(r"\brto\b", re.IGNORECASE), "rto_minutes"),
    (re.compile(r"\brpo\b", re.IGNORECASE), "rpo_minutes"),
)


def _mentions_any(text: str, needles: tuple[str, ...]) -> list[str]:
    """Return the subset of `needles` that appear (case-insensitive) in `text`."""
    lowered = text.lower()
    return [n for n in needles if n.lower() in lowered]


def _detect_api_mismatch(
    ba: BusinessRequirementsDraft, sa: SolutionArchitectureDraft
) -> list[StreamConflict]:
    """R1 — BA asks for REST/GraphQL/gRPC; SA API-layer choice must reflect it."""
    joined_ba = " ".join(
        [fr.description for fr in ba.functional_requirements]
        + [fr.title for fr in ba.functional_requirements]
        + ba.success_criteria
        + list(ba.scope.get("in_scope", []))
    )
    ba_protocols = _mentions_any(joined_ba, _API_PROTOCOLS)
    if not ba_protocols:
        return []

    api_choices = [
        choice for choice in sa.tech_stack if choice.layer.lower() in {"api", "gateway"}
    ]
    sa_api_text = " ".join(c.choice + " " + c.rationale for c in api_choices) or " ".join(
        c.choice for c in sa.tech_stack
    )
    sa_matches = _mentions_any(sa_api_text, tuple(ba_protocols))

    if sa_matches:
        return []

    return [
        StreamConflict(
            streams=["S3a", "S3b"],
            topic="api_layer_protocol",
            description=(
                f"BA references API protocol(s) {ba_protocols} but SA tech_stack "
                f"API-layer entry does not name any of them "
                f"(api_choices={[c.choice for c in api_choices]})."
            ),
            severity="HIGH",
            proposed_resolution=(
                f"Update SA API-layer choice to match {ba_protocols[0]} or flag the divergence "
                "with the bid manager before S5."
            ),
        )
    ]


def _detect_compliance_gap(
    sa: SolutionArchitectureDraft, domain: DomainNotes
) -> list[StreamConflict]:
    """R2 — Hot compliance frameworks require a security-minded SA pattern."""
    hot_frameworks = [
        item.framework
        for item in domain.compliance
        if item.applies and any(h.lower() in item.framework.lower() for h in _COMPLIANCE_HOT)
    ]
    if not hot_frameworks:
        return []

    security_text = " ".join(
        pattern.name + " " + pattern.description for pattern in sa.architecture_patterns
    )
    integrations_text = " ".join(sa.integrations)
    stack_text = " ".join(c.choice + " " + c.rationale for c in sa.tech_stack)
    combined = " ".join((security_text, integrations_text, stack_text))

    if _mentions_any(combined, _SECURITY_KEYWORDS):
        return []

    return [
        StreamConflict(
            streams=["S3b", "S3c"],
            topic="compliance_security_pattern",
            description=(
                f"Domain compliance requires {hot_frameworks} but SA architecture_patterns "
                "do not mention segmentation / encryption / audit / access-control "
                "safeguards."
            ),
            severity="HIGH",
            proposed_resolution=(
                "Add a security-oriented pattern to SA (e.g. network segmentation, "
                "at-rest encryption, or audit logging) that maps to the affected "
                "compliance framework."
            ),
        )
    ]


def _detect_nfr_field_mismatch(
    ba: BusinessRequirementsDraft, sa: SolutionArchitectureDraft
) -> list[StreamConflict]:
    """R3 — BA success_criteria mentions NFR keys; SA must declare matching targets."""
    criteria_text = " ".join(ba.success_criteria)
    if not criteria_text.strip():
        return []

    missing: list[str] = []
    for pattern, key in _NFR_TOKEN_TO_KEY:
        if pattern.search(criteria_text) and key not in sa.nfr_targets:
            missing.append(key)

    if not missing:
        return []

    return [
        StreamConflict(
            streams=["S3a", "S3b"],
            topic="nfr_target_coverage",
            description=(
                f"BA success criteria reference NFR concerns but SA nfr_targets is "
                f"missing key(s): {missing}."
            ),
            severity="MEDIUM",
            proposed_resolution=(
                f"Ask SA to declare explicit targets for {missing} or justify why "
                "they are not applicable."
            ),
        )
    ]


def _readiness(
    ba: BusinessRequirementsDraft,
    sa: SolutionArchitectureDraft,
    domain: DomainNotes,
) -> dict[str, float]:
    return {
        "S3a": round(ba.confidence, 2),
        "S3b": round(sa.confidence, 2),
        "S3c": round(domain.confidence, 2),
        "overall": round(
            READINESS_WEIGHTS["ba"] * ba.confidence
            + READINESS_WEIGHTS["sa"] * sa.confidence
            + READINESS_WEIGHTS["domain"] * domain.confidence,
            2,
        ),
    }


def build_convergence_report(payload: ConvergenceInput) -> ConvergenceReport:
    """Pure function that emits the convergence report — easy to unit-test."""
    readiness = _readiness(payload.ba_draft, payload.sa_draft, payload.domain_notes)

    conflicts: list[StreamConflict] = []
    conflicts.extend(_detect_api_mismatch(payload.ba_draft, payload.sa_draft))
    conflicts.extend(_detect_compliance_gap(payload.sa_draft, payload.domain_notes))
    conflicts.extend(_detect_nfr_field_mismatch(payload.ba_draft, payload.sa_draft))

    unified = (
        f"Unified view for bid {payload.bid_id}. "
        f"BA functional items: {len(payload.ba_draft.functional_requirements)}. "
        f"SA patterns: {len(payload.sa_draft.architecture_patterns)}. "
        f"Compliance obligations: {len(payload.domain_notes.compliance)}. "
        f"Conflicts detected: {len(conflicts)}."
    )

    open_questions: list[str] = []
    if readiness["overall"] < READINESS_GATE:
        laggards = [
            stream
            for stream in ("S3a", "S3b", "S3c")
            if readiness[stream] < 0.70
        ]
        open_questions.append(
            f"Overall readiness {readiness['overall']:.2f} below gate {READINESS_GATE:.2f}; "
            f"streams below 0.70: {laggards or 'none'}."
        )
    if not payload.ba_draft.success_criteria:
        open_questions.append("Success criteria not yet defined by BA stream.")
    if conflicts and not any(q.startswith("Conflict") for q in open_questions):
        open_questions.append(
            f"{len(conflicts)} cross-stream conflict(s) require bid-manager review."
        )

    return ConvergenceReport(
        bid_id=payload.bid_id,
        unified_summary=unified,
        readiness=readiness,
        conflicts=conflicts,
        open_questions=open_questions,
    )


@activity.defn(name="convergence_activity")
async def convergence_activity(payload: ConvergenceInput) -> ConvergenceReport:
    """Merge BA / SA / Domain streams; apply heuristic conflict rules + readiness gate."""
    activity.logger.info("convergence.start bid_id=%s", payload.bid_id)
    report = build_convergence_report(payload)
    activity.logger.info(
        "convergence.done bid_id=%s readiness=%s conflicts=%d questions=%d",
        payload.bid_id,
        report.readiness,
        len(report.conflicts),
        len(report.open_questions),
    )
    return report
