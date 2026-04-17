"""Unit tests for S4 convergence heuristics (pure function — no Temporal needed)."""

from __future__ import annotations

from uuid import uuid4

from activities.convergence import (
    READINESS_GATE,
    build_convergence_report,
)
from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
)
from workflows.artifacts import (
    ArchitecturePattern,
    ComplianceItem,
    ConvergenceInput,
    DomainNotes,
    DomainPractice,
    SolutionArchitectureDraft,
    TechnicalRisk,
    TechStackChoice,
)


def _ba(
    *,
    api_protocol: str | None = "REST",
    success_criteria: list[str] | None = None,
    confidence: float = 0.8,
) -> BusinessRequirementsDraft:
    bid_id = uuid4()
    fr_text = (
        f"Expose a {api_protocol} API for account lookup"
        if api_protocol
        else "Expose an API for account lookup"
    )
    return BusinessRequirementsDraft(
        bid_id=bid_id,
        executive_summary="Summary.",
        business_objectives=["Modernise banking stack"],
        scope={"in_scope": ["Account API"], "out_of_scope": []},
        functional_requirements=[
            FunctionalRequirement(
                id="REQ-001",
                title="Account API",
                description=fr_text,
                priority="MUST",
                rationale="Core RFP ask.",
            )
        ],
        assumptions=[],
        constraints=[],
        success_criteria=success_criteria
        if success_criteria is not None
        else ["<200ms p95 latency", "99.9% availability"],
        risks=[
            RiskItem(
                title="Legacy integration",
                likelihood="MEDIUM",
                impact="HIGH",
                mitigation="Spike week 1.",
            )
        ],
        similar_projects=[],
        confidence=confidence,
        sources=[],
    )


def _sa(
    *,
    api_choice: str = "NestJS REST",
    include_security_pattern: bool = True,
    nfr_targets: dict[str, str] | None = None,
    confidence: float = 0.8,
) -> SolutionArchitectureDraft:
    bid_id = uuid4()
    patterns: list[ArchitecturePattern] = []
    if include_security_pattern:
        patterns.append(
            ArchitecturePattern(
                name="Network segmentation",
                description="CDE segmented with audit logging.",
                applies_to=["REQ-001"],
            )
        )
    patterns.append(
        ArchitecturePattern(
            name="Edge API gateway",
            description="Rate limit + auth.",
            applies_to=["REQ-001"],
        )
    )
    return SolutionArchitectureDraft(
        bid_id=bid_id,
        tech_stack=[
            TechStackChoice(layer="API", choice=api_choice, rationale="Matches RFP ask."),
            TechStackChoice(
                layer="Datastore",
                choice="PostgreSQL 16",
                rationale="ACID.",
            ),
        ],
        architecture_patterns=patterns,
        nfr_targets=(
            nfr_targets
            if nfr_targets is not None
            else {
                "availability": "99.9%",
                "p95_latency_ms": "200",
                "rto_minutes": "30",
                "rpo_minutes": "5",
            }
        ),
        technical_risks=[
            TechnicalRisk(
                title="API contract drift",
                likelihood="LOW",
                impact="MEDIUM",
                mitigation="Versioned schemas.",
            )
        ],
        integrations=["Identity (SSO)"],
        confidence=confidence,
        sources=[],
    )


def _domain(
    *,
    hot_framework: str | None = "PCI DSS",
    confidence: float = 0.8,
) -> DomainNotes:
    bid_id = uuid4()
    compliance = []
    if hot_framework:
        compliance.append(
            ComplianceItem(
                framework=hot_framework,
                requirement="Cardholder data encrypted end-to-end.",
                applies=True,
            )
        )
    compliance.append(
        ComplianceItem(
            framework="ISO 27001",
            requirement="Baseline ISMS.",
            applies=True,
        )
    )
    return DomainNotes(
        bid_id=bid_id,
        industry="banking",
        compliance=compliance,
        best_practices=[
            DomainPractice(title="Data classification", description="Tag PII vs CDE."),
        ],
        industry_constraints=["APAC change-window restrictions."],
        glossary={"CDE": "Cardholder Data Environment"},
        confidence=confidence,
        sources=[],
    )


def _input(ba: BusinessRequirementsDraft, sa: SolutionArchitectureDraft, domain: DomainNotes) -> ConvergenceInput:
    return ConvergenceInput(
        bid_id=ba.bid_id,
        ba_draft=ba,
        sa_draft=sa,
        domain_notes=domain,
    )


def test_convergence_clean_case_has_no_conflicts() -> None:
    report = build_convergence_report(_input(_ba(), _sa(), _domain()))
    assert report.conflicts == []
    assert report.readiness["overall"] >= READINESS_GATE
    assert all(q != "" for q in report.open_questions)


def test_convergence_flags_api_protocol_mismatch() -> None:
    # BA asks for GraphQL, SA ships a REST API → R1 HIGH.
    ba = _ba(api_protocol="GraphQL")
    sa = _sa(api_choice="NestJS REST")
    report = build_convergence_report(_input(ba, sa, _domain()))
    topics = [c.topic for c in report.conflicts]
    assert "api_layer_protocol" in topics
    api_conflict = next(c for c in report.conflicts if c.topic == "api_layer_protocol")
    assert api_conflict.severity == "HIGH"
    assert "S3a" in api_conflict.streams and "S3b" in api_conflict.streams


def test_convergence_flags_compliance_without_security_pattern() -> None:
    # Domain requires PCI DSS, but SA has no security-oriented pattern → R2 HIGH.
    sa = _sa(include_security_pattern=False)
    report = build_convergence_report(_input(_ba(), sa, _domain(hot_framework="PCI DSS")))
    topics = [c.topic for c in report.conflicts]
    assert "compliance_security_pattern" in topics
    compliance_conflict = next(
        c for c in report.conflicts if c.topic == "compliance_security_pattern"
    )
    assert compliance_conflict.severity == "HIGH"


def test_convergence_flags_missing_nfr_target_keys() -> None:
    # BA mentions latency + availability; SA declares neither → R3 MEDIUM.
    ba = _ba(success_criteria=["p95 latency under 200ms", "99.9% uptime"])
    sa = _sa(nfr_targets={"rto_minutes": "30"})
    report = build_convergence_report(_input(ba, sa, _domain(hot_framework=None)))
    nfr_conflict = next(c for c in report.conflicts if c.topic == "nfr_target_coverage")
    assert nfr_conflict.severity == "MEDIUM"
    # Both missing keys should be named in the description.
    assert "p95_latency_ms" in nfr_conflict.description
    assert "availability" in nfr_conflict.description


def test_convergence_readiness_weights_and_gate() -> None:
    # Low BA confidence should drag overall readiness below gate even with high SA/Domain.
    ba = _ba(confidence=0.4)
    sa = _sa(confidence=0.9)
    domain = _domain(confidence=0.9)
    report = build_convergence_report(_input(ba, sa, domain))
    expected_overall = round(0.40 * 0.4 + 0.35 * 0.9 + 0.25 * 0.9, 2)
    assert report.readiness["overall"] == expected_overall
    assert report.readiness["overall"] < READINESS_GATE
    assert any(
        "below gate" in q or "readiness" in q.lower() for q in report.open_questions
    )
