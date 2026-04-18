"""Unit tests for S0/S1/S2 activities (bypass Temporal runtime)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from activities.assembly import assembly_activity
from activities.intake import intake_activity
from activities.scoping import scoping_activity
from activities.triage import triage_activity
from tests.fixtures.bid_states import full_bid_m, minimal_bid_s
from workflows.models import BidCard, IntakeInput


def _intake(text: str, *, client: str = "Acme Bank", industry: str = "banking") -> IntakeInput:
    return IntakeInput(
        client_name=client,
        rfp_text=text,
        deadline=datetime.now(timezone.utc) + timedelta(days=45),
        region="APAC",
        industry=industry,
    )


@pytest.mark.asyncio
async def test_intake_activity_basic() -> None:
    text = (
        "Background: Modernize core banking.\n"
        "- The system shall expose a REST API for account lookup\n"
        "- Must integrate with AWS and support Kubernetes\n"
        "- Users should be able to view transactions in React\n"
        "- Compliance: HIPAA is out of scope; PCI DSS applies\n"
    )
    card = await intake_activity(_intake(text))

    assert card.client_name == "Acme Bank"
    assert card.industry == "banking"
    assert card.estimated_profile in {"S", "M", "L", "XL"}
    assert {"api", "aws", "kubernetes", "react", "pci"}.issubset(set(card.technology_keywords))
    assert len(card.requirements_raw) >= 4


@pytest.mark.asyncio
async def test_intake_activity_profile_sizing() -> None:
    small = await intake_activity(_intake("Short RFP."))
    large = await intake_activity(_intake("x " * 5000))
    assert small.estimated_profile == "S"
    assert large.estimated_profile in {"L", "XL"}


def _card(
    *,
    industry: str = "banking",
    profile: str = "M",
    keywords: list[str] | None = None,
    reqs: int = 5,
) -> BidCard:
    return BidCard(
        bid_id=uuid4(),
        client_name="Acme",
        industry=industry,
        region="APAC",
        deadline=datetime.now(timezone.utc) + timedelta(days=30),
        scope_summary="summary",
        technology_keywords=keywords or [],
        estimated_profile=profile,  # type: ignore[arg-type]
        requirements_raw=[f"requirement {i} shall do X" for i in range(reqs)],
    )


@pytest.mark.asyncio
async def test_triage_activity_bid() -> None:
    card = _card(
        industry="banking",
        profile="M",
        keywords=["api", "microservices", "kubernetes", "aws", "data"],
        reqs=4,
    )
    decision = await triage_activity(card)
    assert decision.recommendation == "BID"
    assert decision.overall_score >= 60.0
    assert set(decision.score_breakdown.keys()) == {
        "win_probability",
        "resource_availability",
        "technical_fit",
        "strategic_value",
        "timeline_feasibility",
    }


@pytest.mark.asyncio
async def test_triage_activity_no_bid() -> None:
    card = _card(industry="retail", profile="XL", keywords=[], reqs=200)
    decision = await triage_activity(card)
    assert decision.recommendation == "NO_BID"
    assert decision.overall_score < 60.0


@pytest.mark.asyncio
async def test_scoping_activity_decomposition() -> None:
    card = BidCard(
        bid_id=uuid4(),
        client_name="Acme",
        industry="healthcare",
        region="US",
        deadline=datetime.now(timezone.utc) + timedelta(days=30),
        scope_summary="s",
        technology_keywords=["api"],
        estimated_profile="L",
        requirements_raw=[
            "1.1 The system shall allow users to submit claims",
            "2.1 API latency must be under 200ms at p95",
            "3.1 Must comply with HIPAA and encrypt PHI at rest",
            "4.1 Go-live deadline within 6 months",
            "short",
        ],
    )

    result = await scoping_activity(card)
    ids = {atom.id: atom for atom in result.requirement_map}
    categories = {atom.category for atom in result.requirement_map}

    assert "compliance" in categories
    assert "nfr" in categories
    assert "timeline" in categories
    assert "functional" in categories
    assert any(atom.category == "unclear" for atom in result.requirement_map)

    # Stream routing: compliance -> S3c for non-S profile.
    compliance_ids = [a.id for a in result.requirement_map if a.category == "compliance"]
    assert all(cid in result.stream_assignments.get("S3c", []) for cid in compliance_ids)

    # Team suggestion lookup honors profile.
    assert result.team_suggestion["ba"] >= 2
    assert all(a.id.startswith("REQ-") for a in ids.values())


@pytest.mark.asyncio
async def test_assembly_activity_uses_real_templates_on_full_bid() -> None:
    """Phase 3.1: assembly activity renders all 7 sections via Jinja."""
    payload = full_bid_m()
    pkg = await assembly_activity(payload)
    headings = [s.heading for s in pkg.sections]
    assert headings == [
        "Cover Page",
        "Executive Summary",
        "Business Requirements",
        "Technical Approach",
        "WBS + Estimation",
        "Pricing + Commercials",
        "Terms + Appendix",
    ]
    assert pkg.consistency_checks["rendered_all_sections"] is True
    assert pkg.consistency_checks.get("template_error") is not True


@pytest.mark.asyncio
async def test_assembly_activity_falls_back_on_template_error(monkeypatch) -> None:
    """When render_package raises RendererError the activity emits the stub shape."""
    from activities import assembly as assembly_module
    from assembly.renderer import RendererError

    def _boom(_payload) -> None:
        raise RendererError("template library corrupt")

    monkeypatch.setattr(assembly_module, "render_package", _boom)
    pkg = await assembly_activity(full_bid_m())
    # Stub has the legacy 5 sections, not 7.
    assert len(pkg.sections) == 5
    assert pkg.consistency_checks.get("template_error") is True
    assert pkg.consistency_checks.get("rendered_all_sections") is False


@pytest.mark.asyncio
async def test_assembly_activity_handles_bid_s_null_pricing_and_hld() -> None:
    pkg = await assembly_activity(minimal_bid_s())
    assert len(pkg.sections) == 7
    pricing = next(s for s in pkg.sections if s.heading == "Pricing + Commercials")
    assert "Not applicable" in pricing.body_markdown


@pytest.mark.asyncio
async def test_scoping_small_profile_folds_compliance_into_s3a() -> None:
    card = BidCard(
        bid_id=uuid4(),
        client_name="Acme",
        industry="healthcare",
        region="US",
        deadline=datetime.now(timezone.utc) + timedelta(days=30),
        scope_summary="s",
        technology_keywords=[],
        estimated_profile="S",
        requirements_raw=["Must comply with HIPAA", "The system shall allow login"],
    )
    result = await scoping_activity(card)
    assert "S3c" not in result.stream_assignments
    assert "S3a" in result.stream_assignments
