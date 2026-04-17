"""Phase 2.1 deterministic stubs for S3a/b/c parallel streams.

These exist so the 11-state DAG can be wired + verified end-to-end without
ANTHROPIC_API_KEY. Phase 2.2 swaps these for the real LangGraph agents
(`agents/ba_agent.py`, `agents/sa_agent.py` [tbd], `agents/domain_agent.py` [tbd]).
"""

from __future__ import annotations

import logging
import math

from temporalio import activity

from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
    SimilarProject,
)
from workflows.artifacts import (
    ArchitecturePattern,
    ComplianceItem,
    DomainNotes,
    DomainPractice,
    SolutionArchitectureDraft,
    StreamInput,
    TechnicalRisk,
    TechStackChoice,
)
from workflows.models import RequirementAtom

logger = logging.getLogger(__name__)


def _filter_by_category(reqs: list[RequirementAtom], category: str) -> list[RequirementAtom]:
    return [r for r in reqs if r.category == category]


def _confidence_from_count(n: int, floor: float = 0.4, cap: float = 0.85) -> float:
    """Monotonic 0..1 score — more input requirements → higher confidence.

    Asymptotic curve: 1 - e^(-n/5) clipped to [floor, cap].
    """
    if n <= 0:
        return floor
    raw = 1.0 - math.exp(-n / 5.0)
    return round(max(floor, min(cap, raw)), 2)


# --- S3a Business Analysis stub ---------------------------------------------


@activity.defn(name="ba_analysis_stub_activity")
async def ba_analysis_stub_activity(payload: StreamInput) -> BusinessRequirementsDraft:
    """Deterministic BA draft — mirrors `BusinessRequirementsDraft` shape without LLM."""
    activity.logger.info(
        "ba_stub.start bid_id=%s reqs=%d", payload.bid_id, len(payload.requirements)
    )

    functional_atoms = _filter_by_category(payload.requirements, "functional")
    functional = [
        FunctionalRequirement(
            id=f"FR-{idx:03d}",
            title=atom.text[:80],
            description=atom.text,
            priority="MUST" if idx <= 3 else "SHOULD",
            rationale=f"Derived from {atom.id} ({atom.category}).",
        )
        for idx, atom in enumerate(functional_atoms, start=1)
    ]

    objectives = [
        f"Deliver value to {payload.client_name} within the {payload.industry} sector.",
        "Minimise operational risk during rollout and cutover.",
    ]
    assumptions = [
        "Client provides access to existing systems and stakeholders on-time.",
        "Data migration scope is bounded by the attached requirements list.",
    ]
    success_criteria = [
        "All MUST functional requirements demonstrated in UAT.",
        "NFR targets met under pilot load profile.",
    ]
    risks = [
        RiskItem(
            title="Stakeholder availability",
            likelihood="MEDIUM",
            impact="HIGH",
            mitigation="Weekly steerco + nominated deputies.",
        ),
        RiskItem(
            title="Scope creep on compliance clauses",
            likelihood="MEDIUM",
            impact="MEDIUM",
            mitigation="Change-control gate with BA + compliance sign-off.",
        ),
    ]

    draft = BusinessRequirementsDraft(
        bid_id=payload.bid_id,
        executive_summary=(
            f"Stub BA summary for {payload.client_name}. "
            f"Derived from {len(payload.requirements)} requirement atom(s)."
        ),
        business_objectives=objectives,
        scope={
            "in_scope": [atom.text for atom in functional_atoms[:5]],
            "out_of_scope": ["Legacy system decommissioning unless explicitly requested."],
        },
        functional_requirements=functional,
        assumptions=assumptions,
        constraints=payload.constraints,
        success_criteria=success_criteria,
        risks=risks,
        similar_projects=[
            SimilarProject(
                project_id="KB-SAMPLE-001",
                relevance_score=0.5,
                why_relevant="Placeholder — swap to KB-surfaced projects in Phase 2.2.",
            )
        ],
        confidence=_confidence_from_count(len(functional)),
        sources=[f"bid:{payload.bid_id}", "phase-2.1-stub"],
    )
    activity.logger.info(
        "ba_stub.done bid_id=%s fr=%d risks=%d", payload.bid_id, len(functional), len(risks)
    )
    return draft


# --- S3b Solution Architecture stub -----------------------------------------


_DEFAULT_STACK: tuple[TechStackChoice, ...] = (
    TechStackChoice(layer="API", choice="NestJS + GraphQL", rationale="Aligned with client stack signal."),
    TechStackChoice(layer="Service", choice="Python FastAPI", rationale="Best fit for AI workloads."),
    TechStackChoice(layer="Datastore", choice="PostgreSQL 16", rationale="Compliance + TCO."),
    TechStackChoice(layer="Cache", choice="Redis 7", rationale="Standard session + queue backbone."),
    TechStackChoice(layer="Runtime", choice="Kubernetes", rationale="Elasticity + blue-green rollout."),
)


@activity.defn(name="sa_analysis_stub_activity")
async def sa_analysis_stub_activity(payload: StreamInput) -> SolutionArchitectureDraft:
    """Deterministic SA draft — tech stack + patterns + risks derived from scoping."""
    activity.logger.info(
        "sa_stub.start bid_id=%s reqs=%d", payload.bid_id, len(payload.requirements)
    )

    nfr_atoms = _filter_by_category(payload.requirements, "nfr")
    technical_atoms = _filter_by_category(payload.requirements, "technical")

    nfr_targets = {
        "availability": "99.5% monthly" if not nfr_atoms else "99.9% monthly",
        "p95_latency_ms": "400" if not nfr_atoms else "250",
        "rto_minutes": "60",
        "rpo_minutes": "15",
    }

    patterns = [
        ArchitecturePattern(
            name="Event-driven convergence",
            description="Each bounded context emits domain events; a saga coordinates cross-cutting flows.",
            applies_to=[a.id for a in technical_atoms[:3]] or ["TECH-placeholder"],
        ),
        ArchitecturePattern(
            name="API gateway per edge",
            description="All external clients enter via a single gateway with authentication + rate limiting.",
            applies_to=["security", "integration"],
        ),
    ]

    risks = [
        TechnicalRisk(
            title="Unvalidated NFR targets",
            likelihood="MEDIUM",
            impact="HIGH",
            mitigation="Early spike on latency-critical paths; re-baseline in S5.",
        ),
        TechnicalRisk(
            title="Integration surface ambiguity",
            likelihood="MEDIUM",
            impact="MEDIUM",
            mitigation="API contract review with client before S6 estimation.",
        ),
    ]

    draft = SolutionArchitectureDraft(
        bid_id=payload.bid_id,
        tech_stack=list(_DEFAULT_STACK),
        architecture_patterns=patterns,
        nfr_targets=nfr_targets,
        technical_risks=risks,
        integrations=["Identity (SSO / Keycloak)", "Data warehouse (read-only)"],
        confidence=_confidence_from_count(len(nfr_atoms) + len(technical_atoms)),
        sources=[f"bid:{payload.bid_id}", "phase-2.1-stub"],
    )
    activity.logger.info(
        "sa_stub.done bid_id=%s patterns=%d risks=%d",
        payload.bid_id,
        len(patterns),
        len(risks),
    )
    return draft


# --- S3c Domain Mining stub -------------------------------------------------


_COMPLIANCE_BY_INDUSTRY: dict[str, tuple[tuple[str, str], ...]] = {
    "banking": (
        ("PCI DSS", "Cardholder data must be encrypted at rest and in transit."),
        ("SOX", "Financial reporting controls auditable end-to-end."),
    ),
    "healthcare": (
        ("HIPAA", "PHI access logged; minimum-necessary principle enforced."),
        ("ISO 27001", "Information security management system certified."),
    ),
    "insurance": (
        ("GDPR", "Data subject rights workflows for EU residents."),
        ("Solvency II", "Risk + capital reporting within regulatory timelines."),
    ),
    "retail": (
        ("PCI DSS", "Point-of-sale + e-commerce flows segmented."),
        ("GDPR", "Consent + marketing preference management."),
    ),
    "government": (
        ("ISO 27001", "Information security certification required."),
        ("ISO 9001", "Quality management processes audited."),
    ),
}


def _compliance_for(industry: str) -> list[ComplianceItem]:
    rows = _COMPLIANCE_BY_INDUSTRY.get(
        industry.lower(),
        (
            ("ISO 27001", "Baseline infosec certification assumed for enterprise bids."),
            ("GDPR", "Personal data handling unless scope explicitly excludes it."),
        ),
    )
    return [
        ComplianceItem(framework=framework, requirement=requirement, applies=True)
        for framework, requirement in rows
    ]


@activity.defn(name="domain_mining_stub_activity")
async def domain_mining_stub_activity(payload: StreamInput) -> DomainNotes:
    """Deterministic domain notes — industry compliance + best practices + constraints."""
    activity.logger.info(
        "domain_stub.start bid_id=%s industry=%s", payload.bid_id, payload.industry
    )

    compliance_atoms = _filter_by_category(payload.requirements, "compliance")
    compliance = _compliance_for(payload.industry)
    # Fold any scoping-detected compliance atoms into the checklist.
    for atom in compliance_atoms:
        compliance.append(
            ComplianceItem(
                framework=f"REQ-DERIVED ({atom.id})",
                requirement=atom.text,
                applies=True,
                notes="Detected in RFP scoping pass.",
            )
        )

    best_practices = [
        DomainPractice(
            title=f"{payload.industry.capitalize()} data classification",
            description="Categorise data by sensitivity before integration design.",
        ),
        DomainPractice(
            title="Stakeholder mapping",
            description="Identify regulatory vs business vs operational stakeholders up-front.",
        ),
    ]

    industry_constraints = [
        f"Operating region: {payload.region} — observe local data residency rules.",
        "Change window restrictions typical of this sector.",
    ]

    notes = DomainNotes(
        bid_id=payload.bid_id,
        industry=payload.industry,
        compliance=compliance,
        best_practices=best_practices,
        industry_constraints=industry_constraints,
        glossary={
            "SLA": "Service Level Agreement",
            "RPO": "Recovery Point Objective",
            "RTO": "Recovery Time Objective",
        },
        confidence=_confidence_from_count(len(compliance)),
        sources=[f"bid:{payload.bid_id}", "phase-2.1-stub"],
    )
    activity.logger.info(
        "domain_stub.done bid_id=%s compliance=%d", payload.bid_id, len(compliance)
    )
    return notes


__all__ = [
    "ba_analysis_stub_activity",
    "sa_analysis_stub_activity",
    "domain_mining_stub_activity",
]
