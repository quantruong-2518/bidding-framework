"""Filesystem integration tests for kb_writer.bid_workspace — uses tmp_path only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import frontmatter

from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
    SimilarProject,
)
from kb_writer.bid_workspace import (
    BIDS_DIRNAME,
    REVIEWS_SUBDIR,
    bid_workspace_path,
    ensure_workspace,
    write_snapshot,
)
from workflows.artifacts import (
    ArchitecturePattern,
    ComplianceItem,
    ConvergenceReport,
    DomainNotes,
    DomainPractice,
    HLDComponent,
    HLDDraft,
    Lesson,
    PricingDraft,
    PricingLine,
    ProposalPackage,
    ProposalSection,
    RetrospectiveDraft,
    ReviewComment,
    ReviewRecord,
    SolutionArchitectureDraft,
    StreamConflict,
    SubmissionRecord,
    TechStackChoice,
    TechnicalRisk,
    WBSDraft,
    WBSItem,
)
from workflows.models import BidCard, BidState, ScopingResult, TriageDecision
from workflows.base import RequirementAtom


def _card(bid_id) -> BidCard:
    return BidCard(
        bid_id=bid_id,
        client_name="Acme Bank",
        industry="banking",
        region="APAC",
        deadline=datetime.now(timezone.utc) + timedelta(days=45),
        scope_summary="Modernise core banking platform.",
        technology_keywords=["python", "kubernetes"],
        estimated_profile="M",
        requirements_raw=["shall expose REST APIs"],
    )


def _populated_state(bid_id) -> BidState:
    card = _card(bid_id)
    triage = TriageDecision(
        score_breakdown={"strategic": 0.8, "revenue": 0.7},
        overall_score=78.0,
        recommendation="BID",
        rationale="High strategic fit.",
    )
    scoping = ScopingResult(
        requirement_map=[
            RequirementAtom(id="REQ-001", text="REST API", category="functional"),
            RequirementAtom(id="REQ-002", text="Sub-200ms latency", category="nfr"),
        ],
        stream_assignments={"S3a": ["REQ-001"], "S3b": ["REQ-002"]},
        team_suggestion={"ba": 2, "sa": 3},
    )
    ba = BusinessRequirementsDraft(
        bid_id=bid_id,
        executive_summary="Deliver modernised APIs.",
        business_objectives=["Digital self-service"],
        scope={"in_scope": ["APIs"], "out_of_scope": ["Loan origination"]},
        functional_requirements=[
            FunctionalRequirement(
                id="REQ-001",
                title="REST API",
                description="Expose account lookup REST API.",
                priority="MUST",
                rationale="Core RFP ask.",
            )
        ],
        assumptions=["Existing core is reusable"],
        constraints=["500 MD cap"],
        success_criteria=["<200ms p95 latency"],
        risks=[
            RiskItem(
                title="Mainframe latency",
                likelihood="MEDIUM",
                impact="HIGH",
                mitigation="Spike week 1.",
            )
        ],
        similar_projects=[
            SimilarProject(project_id="PRJ-001", relevance_score=0.8, why_relevant="Same client."),
        ],
        confidence=0.8,
        sources=["kb/projects/acme.md"],
    )
    sa = SolutionArchitectureDraft(
        bid_id=bid_id,
        tech_stack=[
            TechStackChoice(layer="API", choice="NestJS REST", rationale="Matches ask."),
            TechStackChoice(layer="Datastore", choice="PostgreSQL 16", rationale="ACID."),
        ],
        architecture_patterns=[
            ArchitecturePattern(
                name="Network segmentation",
                description="CDE segmentation.",
                applies_to=["REQ-002"],
            )
        ],
        nfr_targets={"availability": "99.9%", "p95_latency_ms": "200"},
        technical_risks=[
            TechnicalRisk(
                title="Schema drift",
                likelihood="LOW",
                impact="MEDIUM",
                mitigation="Versioned contracts.",
            )
        ],
        integrations=["Identity (SSO)"],
        confidence=0.82,
        sources=["kb/patterns/banking.md"],
    )
    domain = DomainNotes(
        bid_id=bid_id,
        industry="banking",
        compliance=[
            ComplianceItem(framework="PCI DSS", requirement="Encrypt cardholder data.", applies=True),
        ],
        best_practices=[
            DomainPractice(title="Tokenisation", description="Tokenise PAN at entry."),
        ],
        industry_constraints=["APAC change window restrictions."],
        glossary={"CDE": "Cardholder Data Environment"},
        confidence=0.78,
        sources=["kb/compliance/apac-banking.md"],
    )
    convergence = ConvergenceReport(
        bid_id=bid_id,
        unified_summary="All three streams aligned.",
        readiness={"S3a": 0.8, "S3b": 0.82, "S3c": 0.78, "overall": 0.80},
        conflicts=[
            StreamConflict(
                streams=["S3b", "S3c"],
                topic="compliance_security_pattern",
                description="PCI requires segmentation.",
                severity="HIGH",
                proposed_resolution="Add segmentation pattern.",
            )
        ],
        open_questions=[],
    )
    hld = HLDDraft(
        bid_id=bid_id,
        architecture_overview="Three-tier.",
        components=[HLDComponent(name="API", responsibility="HTTP ingress")],
        data_flows=["Client -> API"],
        integration_points=["Core banking"],
        security_approach="Defence in depth.",
        deployment_model="Kubernetes blue-green.",
    )
    wbs = WBSDraft(
        bid_id=bid_id,
        items=[
            WBSItem(id="WBS-1", name="Discovery", effort_md=10.0, owner_role="ba"),
            WBSItem(id="WBS-2", name="Build APIs", parent_id="WBS-1", effort_md=50.0, owner_role="sa"),
        ],
        total_effort_md=60.0,
        timeline_weeks=16,
        critical_path=["WBS-1", "WBS-2"],
    )
    pricing = PricingDraft(
        bid_id=bid_id,
        model="fixed_price",
        currency="USD",
        lines=[PricingLine(label="Build", amount=150000.0)],
        subtotal=150000.0,
        margin_pct=20.0,
        total=180000.0,
        scenarios={"conservative": 200000.0},
        notes="Estimate based on 60 MD at blended rate.",
    )
    package = ProposalPackage(
        bid_id=bid_id,
        title="Proposal for Acme Bank",
        sections=[
            ProposalSection(heading="Exec", body_markdown="Summary.", sourced_from=["ba_draft"]),
            ProposalSection(heading="Approach", body_markdown="Stack.", sourced_from=["sa_draft"]),
        ],
        appendices=[],
        consistency_checks={"ba_coverage": True, "pricing_matches_wbs": True},
    )
    review = ReviewRecord(
        bid_id=bid_id,
        reviewer_role="bid_manager",
        reviewer="Alice Nguyen",
        verdict="APPROVED",
        comments=[ReviewComment(section="Exec", severity="NIT", message="Tweak wording.")],
        reviewed_at=datetime.now(timezone.utc),
    )
    submission = SubmissionRecord(
        bid_id=bid_id,
        submitted_at=datetime.now(timezone.utc),
        channel="portal",
        confirmation_id="SUB-12345678",
        package_checksum="abc123",
        checklist={"sent_to_portal": True, "notified_client": True},
    )
    retrospective = RetrospectiveDraft(
        bid_id=bid_id,
        outcome="PENDING",
        lessons=[Lesson(title="Spike mainframe early", category="process", detail="Saves 5 MD.")],
        kb_updates=["kb/lessons/acme-2026.md"],
    )

    return BidState(
        bid_id=bid_id,
        current_state="S11_DONE",
        bid_card=card,
        triage=triage,
        scoping=scoping,
        profile="M",
        ba_draft=ba,
        sa_draft=sa,
        domain_notes=domain,
        convergence=convergence,
        hld=hld,
        wbs=wbs,
        pricing=pricing,
        proposal_package=package,
        reviews=[review],
        submission=submission,
        retrospective=retrospective,
    )


def test_ensure_workspace_creates_bid_and_reviews_dirs(tmp_path: Path) -> None:
    bid_id = uuid4()
    root = ensure_workspace(tmp_path, bid_id)

    expected = tmp_path / BIDS_DIRNAME / str(bid_id)
    assert root == expected
    assert root.is_dir()
    assert (root / REVIEWS_SUBDIR).is_dir()


def test_write_snapshot_populates_every_file_at_s11_done(tmp_path: Path) -> None:
    bid_id = uuid4()
    state = _populated_state(bid_id)

    receipt = write_snapshot(tmp_path, state)

    root = bid_workspace_path(tmp_path, bid_id)
    expected_files = {
        "00-bid-card.md",
        "01-triage.md",
        "02-scoping.md",
        "03-ba.md",
        "03-sa.md",
        "03-domain.md",
        "04-convergence.md",
        "05-hld.md",
        "06-wbs.md",
        "07-pricing.md",
        "08-proposal.md",
        "10-submission.md",
        "11-retrospective.md",
        "index.md",
        f"{REVIEWS_SUBDIR}/01-alice-nguyen.md",
    }
    written = set(receipt.files_written)
    assert expected_files <= written, f"missing: {expected_files - written}"
    assert receipt.errors == []

    # Each file actually exists with `kind: bid_output` frontmatter.
    for rel in expected_files:
        path = root / rel
        assert path.is_file(), f"{path} not written"
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
        assert post.metadata["kind"] == "bid_output"
        assert post.metadata["bid_id"] == str(bid_id)


def test_write_snapshot_skips_none_artifacts_and_still_writes_index(tmp_path: Path) -> None:
    bid_id = uuid4()
    state = BidState(
        bid_id=bid_id,
        current_state="S0",
        bid_card=_card(bid_id),
    )

    receipt = write_snapshot(tmp_path, state, phase="S0_DONE")

    assert "00-bid-card.md" in receipt.files_written
    assert "index.md" in receipt.files_written
    # Every downstream file should be reported as skipped.
    for skipped in (
        "01-triage.md",
        "03-ba.md",
        "08-proposal.md",
        "11-retrospective.md",
    ):
        assert skipped in receipt.files_skipped

    root = bid_workspace_path(tmp_path, bid_id)
    # Index links exist but only for present artifacts.
    index_text = (root / "index.md").read_text(encoding="utf-8")
    assert "[[00-bid-card|00 Bid Card]]" in index_text
    assert "[[05-hld" not in index_text


def test_write_snapshot_is_idempotent_on_repeat(tmp_path: Path) -> None:
    bid_id = uuid4()
    state = _populated_state(bid_id)

    receipt_1 = write_snapshot(tmp_path, state)
    receipt_2 = write_snapshot(tmp_path, state)

    root = bid_workspace_path(tmp_path, bid_id)
    # Same files both times; no growth in the workspace tree.
    file_count = sum(1 for _ in root.rglob("*") if _.is_file())
    assert file_count == len(receipt_1.files_written) == len(receipt_2.files_written)
    assert receipt_1.errors == receipt_2.errors == []
