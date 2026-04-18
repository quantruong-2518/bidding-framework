"""Phase 3.1 — reusable :class:`AssemblyInput` fixtures for renderer + consistency tests.

Three shapes mirror the profile pipeline matrix + edge cases:

``full_bid_m()``
    Bid-M with all 7 phases populated: HLD, pricing, convergence, reviews.

``minimal_bid_s()``
    Bid-S fast-path — no HLD, no pricing. Templates 03 + 05 must emit the
    "Not applicable" placeholder via the ``section_or_na`` macro.

``edge_bid()``
    Zero-line WBS + pricing with zero subtotal. Forces the consistency
    checker to evaluate divide-by-zero / empty-line branches.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
)
from workflows.artifacts import (
    ArchitecturePattern,
    AssemblyInput,
    ComplianceItem,
    ConvergenceReport,
    DomainNotes,
    DomainPractice,
    HLDComponent,
    HLDDraft,
    PricingDraft,
    PricingLine,
    ReviewRecord,
    SolutionArchitectureDraft,
    TechStackChoice,
    TechnicalRisk,
    WBSDraft,
    WBSItem,
)
from workflows.base import RequirementAtom
from workflows.models import BidCard, BidProfile, ScopingResult, TriageDecision


_DEFAULT_BID_ID = UUID("11111111-1111-1111-1111-111111111111")
_GENERATED_AT = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)


def _bid_card(profile: BidProfile, client_name: str = "Acme Bank") -> BidCard:
    return BidCard(
        bid_id=_DEFAULT_BID_ID,
        client_name=client_name,
        industry="banking",
        region="APAC",
        deadline=_GENERATED_AT + timedelta(days=60),
        scope_summary="Digital core modernization",
        technology_keywords=["microservices", "kafka"],
        estimated_profile=profile,
        requirements_raw=["REQ-001"],
        created_at=_GENERATED_AT,
    )


def _ba_draft() -> BusinessRequirementsDraft:
    return BusinessRequirementsDraft(
        bid_id=_DEFAULT_BID_ID,
        executive_summary="Modernize the Acme Bank core platform with secure APIs.",
        business_objectives=["Reduce batch windows", "Enable real-time payments"],
        scope={
            "in_scope": ["REST APIs", "Event streaming"],
            "out_of_scope": ["Branch teller UI"],
        },
        functional_requirements=[
            FunctionalRequirement(
                id="REQ-001",
                title="Account lookup REST API",
                description="Expose GET /accounts/{id}",
                priority="MUST",
                rationale="Core to card authorization",
            ),
            FunctionalRequirement(
                id="REQ-002",
                title="Audit trail",
                description="All mutations append to audit log",
                priority="SHOULD",
                rationale="Regulatory",
            ),
        ],
        assumptions=["Existing IAM remains"],
        risks=[
            RiskItem(title="Core cutover", likelihood="MEDIUM", impact="HIGH", mitigation="Dual-run")
        ],
        confidence=0.82,
        sources=["kb/banking-ref.md"],
    )


def _sa_draft() -> SolutionArchitectureDraft:
    return SolutionArchitectureDraft(
        bid_id=_DEFAULT_BID_ID,
        tech_stack=[
            TechStackChoice(layer="API", choice="NestJS", rationale="Team familiarity"),
            TechStackChoice(layer="Streaming", choice="Kafka", rationale="At-least-once"),
        ],
        architecture_patterns=[
            ArchitecturePattern(
                name="CQRS",
                description="Split read + write models",
                applies_to=["API"],
            )
        ],
        nfr_targets={"availability": "99.9%", "latency_p95_ms": "150"},
        technical_risks=[
            TechnicalRisk(
                title="Kafka partition skew",
                likelihood="LOW",
                impact="MEDIUM",
                mitigation="Hash on account-id",
            )
        ],
        integrations=["Core ledger", "Card scheme"],
        confidence=0.80,
        sources=["kb/patterns.md"],
    )


def _domain_notes() -> DomainNotes:
    return DomainNotes(
        bid_id=_DEFAULT_BID_ID,
        industry="banking",
        compliance=[
            ComplianceItem(
                framework="PCI DSS",
                requirement="Encrypt PAN at rest + in transit",
                applies=True,
            )
        ],
        best_practices=[
            DomainPractice(
                title="Idempotent transfers",
                description="All money-moves carry an idempotency key",
            )
        ],
        industry_constraints=["Regulator approval on core changes"],
        glossary={"PAN": "Primary Account Number"},
        confidence=0.78,
        sources=["kb/compliance.md"],
    )


def _convergence() -> ConvergenceReport:
    return ConvergenceReport(
        bid_id=_DEFAULT_BID_ID,
        unified_summary="All three streams agree on the core API-first delivery shape.",
        readiness={"ba": 0.82, "sa": 0.80, "domain": 0.78},
        conflicts=[],
        open_questions=["Cutover window for live migration?"],
    )


def _hld() -> HLDDraft:
    return HLDDraft(
        bid_id=_DEFAULT_BID_ID,
        architecture_overview="Event-driven microservices fronted by BFF.",
        components=[
            HLDComponent(name="AccountService", responsibility="CRUD on accounts"),
            HLDComponent(name="LedgerEmitter", responsibility="Emit balance deltas"),
        ],
        data_flows=["Client -> BFF -> AccountService -> Kafka"],
        integration_points=["Card scheme webhook"],
        security_approach="mTLS + per-service JWT",
        deployment_model="Kubernetes (EKS)",
    )


def _wbs(total_effort_md: float = 205.0, items_empty: bool = False) -> WBSDraft:
    if items_empty:
        return WBSDraft(
            bid_id=_DEFAULT_BID_ID,
            items=[],
            total_effort_md=0.0,
            timeline_weeks=0,
            critical_path=[],
        )
    return WBSDraft(
        bid_id=_DEFAULT_BID_ID,
        items=[
            WBSItem(id="WP-1", name="Discovery + architecture", effort_md=35),
            WBSItem(id="WP-2", name="API build", effort_md=90),
            WBSItem(id="WP-3", name="Integration + hardening", effort_md=80),
        ],
        total_effort_md=total_effort_md,
        timeline_weeks=16,
        critical_path=["WP-1", "WP-2"],
    )


def _pricing(subtotal: float = 200_000.0, margin: float = 20.0) -> PricingDraft:
    total = subtotal * (1.0 + margin / 100.0)
    return PricingDraft(
        bid_id=_DEFAULT_BID_ID,
        model="fixed_price",
        currency="USD",
        lines=[
            PricingLine(label="Professional services", amount=subtotal * 0.8, unit="USD"),
            PricingLine(label="Tooling + licenses", amount=subtotal * 0.2, unit="USD"),
        ],
        subtotal=subtotal,
        margin_pct=margin,
        total=total,
        scenarios={"accelerated": total * 1.15},
        notes="Indicative — 30-day validity.",
    )


def _scoping() -> ScopingResult:
    return ScopingResult(
        requirement_map=[
            RequirementAtom(
                id="REQ-001",
                text="Expose account lookup",
                category="functional",
            ),
        ],
        stream_assignments={"BA": ["REQ-001"], "SA": ["REQ-001"]},
        team_suggestion={"BA": 1, "SA": 2},
    )


def _triage() -> TriageDecision:
    return TriageDecision(
        score_breakdown={"strategic_fit": 80, "capability_match": 75},
        overall_score=77.5,
        recommendation="BID",
        rationale="Strong domain match + deal size above threshold.",
    )


def full_bid_m(*, bid_id: UUID | None = None) -> AssemblyInput:
    """Bid-M with every artifact populated."""
    return AssemblyInput(
        bid_id=bid_id or _DEFAULT_BID_ID,
        title="Proposal for Acme Bank",
        ba_draft=_ba_draft(),
        sa_draft=_sa_draft(),
        domain_notes=_domain_notes(),
        hld=_hld(),
        wbs=_wbs(),
        pricing=_pricing(),
        bid_card=_bid_card(BidProfile.M),
        triage=_triage(),
        scoping=_scoping(),
        convergence=_convergence(),
        reviews=[],
        generated_at=_GENERATED_AT,
    )


def minimal_bid_s(*, bid_id: UUID | None = None) -> AssemblyInput:
    """Bid-S fast-path — HLD + pricing absent."""
    return AssemblyInput(
        bid_id=bid_id or _DEFAULT_BID_ID,
        title="Proposal for Acme Bank (fast-path)",
        ba_draft=_ba_draft(),
        sa_draft=_sa_draft(),
        domain_notes=_domain_notes(),
        hld=None,
        wbs=_wbs(total_effort_md=40.0),
        pricing=None,
        bid_card=_bid_card(BidProfile.S),
        triage=_triage(),
        scoping=_scoping(),
        convergence=_convergence(),
        reviews=[],
        generated_at=_GENERATED_AT,
    )


def edge_bid(*, bid_id: UUID | None = None) -> AssemblyInput:
    """Edge case — zero WBS + pricing with zero subtotal."""
    return AssemblyInput(
        bid_id=bid_id or _DEFAULT_BID_ID,
        title="Edge Proposal",
        ba_draft=_ba_draft(),
        sa_draft=_sa_draft(),
        domain_notes=_domain_notes(),
        hld=_hld(),
        wbs=_wbs(items_empty=True),
        pricing=PricingDraft(
            bid_id=_DEFAULT_BID_ID,
            model="time_and_materials",
            currency="USD",
            lines=[],
            subtotal=0.0,
            margin_pct=0.0,
            total=0.0,
        ),
        bid_card=_bid_card(BidProfile.L),
        triage=_triage(),
        scoping=_scoping(),
        convergence=_convergence(),
        reviews=[
            ReviewRecord(
                bid_id=_DEFAULT_BID_ID,
                reviewer="edge-case-qc",
                reviewer_role="qc",
                verdict="APPROVED",
                comments=[],
                reviewed_at=_GENERATED_AT,
            )
        ],
        generated_at=_GENERATED_AT,
    )


__all__ = ["full_bid_m", "minimal_bid_s", "edge_bid"]
