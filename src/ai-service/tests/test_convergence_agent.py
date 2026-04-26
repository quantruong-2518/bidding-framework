"""Conv 15 — S4 semantic LLM-compare augment via small tier."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.convergence_agent import run_semantic_compare
from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
)
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.artifacts import (
    ArchitecturePattern,
    ComplianceItem,
    DomainNotes,
    DomainPractice,
    SolutionArchitectureDraft,
    StreamConflict,
    TechStackChoice,
    TechnicalRisk,
)


def _ba() -> BusinessRequirementsDraft:
    return BusinessRequirementsDraft(
        bid_id=uuid4(),
        executive_summary="Banking API platform.",
        business_objectives=[],
        scope={"in_scope": ["Account lookup API"], "out_of_scope": []},
        functional_requirements=[
            FunctionalRequirement(
                id="REQ-001", title="REST account lookup", description="x",
                priority="MUST", rationale="y",
            )
        ],
        assumptions=[], constraints=[],
        success_criteria=["p95 < 200ms", "99.95% availability"],
        risks=[RiskItem(title="x", likelihood="LOW", impact="LOW", mitigation="y")],
        similar_projects=[], confidence=0.7, sources=[],
    )


def _sa() -> SolutionArchitectureDraft:
    return SolutionArchitectureDraft(
        bid_id=uuid4(),
        tech_stack=[TechStackChoice(layer="api", choice="FastAPI", rationale="async")],
        architecture_patterns=[ArchitecturePattern(name="CQRS", description="cmd/query")],
        nfr_targets={"p95_latency_ms": "200", "availability": "99.95"},
        technical_risks=[TechnicalRisk(title="DB hot partition",
                                       likelihood="MED", impact="HIGH", mitigation="x")],
        integrations=["Identity provider"],
        confidence=0.7, sources=[],
    )


def _domain() -> DomainNotes:
    return DomainNotes(
        bid_id=uuid4(),
        industry="banking",
        compliance=[ComplianceItem(framework="PCI DSS", requirement="x")],
        best_practices=[DomainPractice(title="audit logs", description="x")],
        industry_constraints=[], glossary={}, confidence=0.8, sources=[],
    )


def _scripted_compare(topics: list[str]) -> ScriptedResponse:
    return ScriptedResponse(
        text=json.dumps(
            {
                "conflicts": [
                    {
                        "streams": ["S3a", "S3b"],
                        "topic": topic,
                        "description": f"semantic mismatch on {topic}",
                        "severity": "MEDIUM",
                        "proposed_resolution": "escalate to bid manager",
                    }
                    for topic in topics
                ]
            }
        ),
        usage=TokenUsage(input_tokens=300, output_tokens=120),
        cost_usd=0.00045,
        model="fake/small",
        provider="fake",
    )


@pytest.mark.asyncio
async def test_semantic_compare_returns_new_conflicts_only() -> None:
    """Topics that already exist in heuristic list are filtered out."""
    fake = FakeLLMClient(_scripted_compare(["api_layer_protocol", "audit_async_gap"]))
    existing = [
        StreamConflict(
            streams=["S3a", "S3b"],
            topic="api_layer_protocol",
            description="heuristic R1",
            severity="HIGH",
            proposed_resolution="x",
        )
    ]
    new, cost = await run_semantic_compare(
        _ba(), _sa(), _domain(), existing,
        bid_id_for_trace="trace-1", client=fake,
    )
    assert [c.topic for c in new] == ["audit_async_gap"]
    assert cost == pytest.approx(0.00045, abs=1e-6)
    assert fake.calls[0].tier == "small"
    assert fake.calls[0].trace_id == "trace-1"
    assert fake.calls[0].node_name == "convergence_agent.semantic_compare"


@pytest.mark.asyncio
async def test_semantic_compare_silent_on_parse_failure() -> None:
    """Garbage JSON → ([], cost). Convergence keeps the heuristic conflicts."""
    fake = FakeLLMClient(ScriptedResponse(text="not even close"))
    new, cost = await run_semantic_compare(
        _ba(), _sa(), _domain(), [],
        bid_id_for_trace="t", client=fake,
    )
    assert new == []
    # Cost still attributed (the call did happen).
    assert cost == 0.0


@pytest.mark.asyncio
async def test_semantic_compare_silent_on_send_exception() -> None:
    """LLM raises mid-call → ([], 0.0). Convergence path is unaffected."""
    fake = FakeLLMClient(ScriptedResponse(raise_error=RuntimeError("boom")))
    new, cost = await run_semantic_compare(
        _ba(), _sa(), _domain(), [],
        bid_id_for_trace="t", client=fake,
    )
    assert new == []
    assert cost == 0.0


@pytest.mark.asyncio
async def test_semantic_compare_handles_zero_new_conflicts() -> None:
    """LLM may legitimately find no new conflicts — that's a success path."""
    fake = FakeLLMClient(_scripted_compare([]))
    new, cost = await run_semantic_compare(
        _ba(), _sa(), _domain(), [],
        bid_id_for_trace="t", client=fake,
    )
    assert new == []
    assert cost == pytest.approx(0.00045, abs=1e-6)


@pytest.mark.asyncio
async def test_semantic_compare_dedup_is_case_insensitive() -> None:
    """`API_LAYER_PROTOCOL` from LLM doesn't slip past `api_layer_protocol` heuristic."""
    fake = FakeLLMClient(_scripted_compare(["API_LAYER_PROTOCOL"]))
    existing = [
        StreamConflict(streams=["S3a"], topic="api_layer_protocol",
                       description="r1", severity="HIGH",
                       proposed_resolution="x")
    ]
    new, _ = await run_semantic_compare(
        _ba(), _sa(), _domain(), existing,
        bid_id_for_trace="t", client=fake,
    )
    assert new == []
