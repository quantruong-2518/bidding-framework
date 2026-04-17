"""Unit tests for kb_writer.templates — frontmatter + content contract, no FS IO."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import frontmatter

from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
    SimilarProject,
)
from kb_writer import templates
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
from workflows.models import BidCard, BidState, TriageDecision


def _parse(md: str) -> frontmatter.Post:
    return frontmatter.loads(md)


def _expect_bid_output(post: frontmatter.Post, *, bid_id, artifact: str, phase: str) -> None:
    assert post.metadata["kind"] == "bid_output"
    assert post.metadata["bid_id"] == str(bid_id)
    assert post.metadata["artifact"] == artifact
    assert post.metadata["phase"] == phase
    assert "generated_at" in post.metadata


def test_render_bid_card_emits_frontmatter_and_content() -> None:
    card = BidCard(
        bid_id=uuid4(),
        client_name="Acme Bank",
        industry="banking",
        region="APAC",
        deadline=datetime.now(timezone.utc) + timedelta(days=30),
        scope_summary="Modernise core platform.",
        technology_keywords=["python", "kubernetes"],
        estimated_profile="M",
        requirements_raw=["shall expose REST APIs"],
    )
    md = templates.render_bid_card(card)
    post = _parse(md)
    _expect_bid_output(post, bid_id=card.bid_id, artifact="bid_card", phase="S0_DONE")
    content = post.content
    assert "Acme Bank" in content
    assert "Modernise core platform." in content
    assert "kubernetes" in content
    assert "shall expose REST APIs" in content


def test_render_ba_contains_all_section_headers() -> None:
    bid_id = uuid4()
    draft = BusinessRequirementsDraft(
        bid_id=bid_id,
        executive_summary="Summary text.",
        business_objectives=["Modernise"],
        scope={"in_scope": ["API"], "out_of_scope": ["Loan origination"]},
        functional_requirements=[
            FunctionalRequirement(
                id="FR-001",
                title="Account lookup API",
                description="Expose REST endpoints.",
                priority="MUST",
                rationale="Core ask.",
            )
        ],
        assumptions=["Existing APIs reusable"],
        constraints=["500 MD cap"],
        success_criteria=["<200ms p95"],
        risks=[
            RiskItem(
                title="Legacy integration",
                likelihood="MEDIUM",
                impact="HIGH",
                mitigation="Week-1 spike",
            )
        ],
        similar_projects=[
            SimilarProject(
                project_id="PRJ-001",
                relevance_score=0.81,
                why_relevant="Same client",
            )
        ],
        confidence=0.75,
        sources=["kb/projects/acme.md"],
    )
    md = templates.render_ba(draft)
    post = _parse(md)
    _expect_bid_output(post, bid_id=bid_id, artifact="ba_draft", phase="S3_DONE")
    content = post.content
    for heading in (
        "Executive summary",
        "Business objectives",
        "In scope",
        "Out of scope",
        "Functional requirements",
        "Risks",
        "Similar projects",
        "Sources",
    ):
        assert heading in content, f"missing heading: {heading}"
    assert "FR-001" in content
    assert "Legacy integration" in content


def test_render_convergence_renders_conflicts_and_readiness() -> None:
    bid_id = uuid4()
    report = ConvergenceReport(
        bid_id=bid_id,
        unified_summary="Summary.",
        readiness={"S3a": 0.8, "S3b": 0.7, "S3c": 0.6, "overall": 0.72},
        conflicts=[
            StreamConflict(
                streams=["S3a", "S3b"],
                topic="api_layer_protocol",
                description="REST vs GraphQL drift",
                severity="HIGH",
                proposed_resolution="Align SA API choice",
            )
        ],
        open_questions=["Readiness below gate"],
    )
    md = templates.render_convergence(report)
    post = _parse(md)
    _expect_bid_output(post, bid_id=bid_id, artifact="convergence", phase="S4_DONE")
    content = post.content
    assert "api_layer_protocol" in content
    assert "HIGH" in content
    assert "0.72" in content
    assert "Readiness below gate" in content


def test_render_proposal_renders_sections_and_checks() -> None:
    bid_id = uuid4()
    pkg = ProposalPackage(
        bid_id=bid_id,
        title="Proposal for Acme Bank",
        sections=[
            ProposalSection(
                heading="Executive summary",
                body_markdown="Concise summary.",
                sourced_from=["ba_draft"],
            ),
            ProposalSection(
                heading="Technical approach",
                body_markdown="NestJS + PostgreSQL.",
                sourced_from=["sa_draft", "hld"],
            ),
        ],
        appendices=["Ref A"],
        consistency_checks={"ba_coverage": True, "pricing_matches_wbs": False},
    )
    md = templates.render_proposal(pkg)
    post = _parse(md)
    _expect_bid_output(post, bid_id=bid_id, artifact="proposal_package", phase="S8_DONE")
    content = post.content
    assert "Executive summary" in content
    assert "Technical approach" in content
    assert "sourced from: ba_draft" in content
    assert "❌" in content  # pricing_matches_wbs false


def test_render_index_builds_wiki_links_for_present_artifacts() -> None:
    bid_id = uuid4()
    card = BidCard(
        bid_id=bid_id,
        client_name="Acme",
        industry="banking",
        region="APAC",
        deadline=datetime.now(timezone.utc) + timedelta(days=30),
        scope_summary="scope",
        technology_keywords=[],
        estimated_profile="M",
        requirements_raw=[],
    )
    review = ReviewRecord(
        bid_id=bid_id,
        reviewer_role="bid_manager",
        reviewer="alice",
        verdict="APPROVED",
        comments=[
            ReviewComment(section="Exec", severity="NIT", message="tweak wording"),
        ],
        reviewed_at=datetime.now(timezone.utc),
    )
    state = BidState(
        bid_id=bid_id,
        current_state="S9",
        bid_card=card,
        triage=TriageDecision(
            score_breakdown={"strategic": 0.8},
            overall_score=80.0,
            recommendation="BID",
            rationale="fit",
        ),
        reviews=[review],
    )
    md = templates.render_index(state)
    post = _parse(md)
    assert post.metadata["artifact"] == "index"
    content = post.content
    assert "[[00-bid-card|00 Bid Card]]" in content
    assert "[[01-triage|01 Triage]]" in content
    assert "[[09-reviews/01|09 Review round 1]]" in content
    # Artifacts not yet produced should be absent.
    assert "[[05-hld" not in content
