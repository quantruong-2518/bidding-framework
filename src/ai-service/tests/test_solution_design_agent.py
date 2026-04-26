"""Conv 14 — S5 Solution Design real LLM via flagship synth + small critique."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.solution_design_agent import run_solution_design_agent
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.artifacts import (
    ArchitecturePattern,
    ConvergenceReport,
    SolutionArchitectureDraft,
    SolutionDesignInput,
    TechStackChoice,
    TechnicalRisk,
)


def _sample_input() -> SolutionDesignInput:
    bid_id = uuid4()
    return SolutionDesignInput(
        bid_id=bid_id,
        convergence=ConvergenceReport(
            bid_id=bid_id,
            unified_summary="Banking API platform with strong NFR + PCI DSS compliance.",
            readiness={"ba": 0.8, "sa": 0.85, "domain": 0.9},
            open_questions=["Final SLO for retries"],
        ),
        sa_draft=SolutionArchitectureDraft(
            bid_id=bid_id,
            tech_stack=[
                TechStackChoice(layer="API", choice="FastAPI", rationale="async + types"),
                TechStackChoice(layer="Datastore", choice="Postgres", rationale="ACID"),
            ],
            architecture_patterns=[
                ArchitecturePattern(name="CQRS", description="cmd/query split", applies_to=["api"]),
            ],
            nfr_targets={"latency_p95_ms": "200", "availability": "99.95"},
            technical_risks=[
                TechnicalRisk(title="DB hot partition", likelihood="MEDIUM", impact="HIGH",
                              mitigation="sharding"),
            ],
            integrations=["Identity provider", "Core ledger", "Notification bus"],
            confidence=0.7,
            sources=[],
        ),
    )


def _scripted_draft() -> ScriptedResponse:
    payload = {
        "architecture_overview": "Layered FastAPI service backed by Postgres with CQRS read paths.",
        "components": [
            {"name": "API Gateway", "responsibility": "ingress + auth", "depends_on": []},
            {"name": "FastAPI Service", "responsibility": "business logic",
             "depends_on": ["API Gateway"]},
            {"name": "Postgres Cluster", "responsibility": "system of record",
             "depends_on": ["FastAPI Service", "GHOST"]},
        ],
        "data_flows": ["Client → API Gateway → FastAPI Service → Postgres Cluster"],
        # Intentionally drops "Notification bus" so the wrapper carries it from SA.
        "integration_points": ["Identity provider", "Core ledger"],
        "security_approach": "Edge JWT, service mTLS, AES-256 at-rest.",
        "deployment_model": "K8s rolling deploys, blue/green for schema changes.",
    }
    return ScriptedResponse(
        text=json.dumps(payload),
        usage=TokenUsage(input_tokens=600, output_tokens=320),
        cost_usd=0.0021,
        model="fake/flagship",
        provider="fake",
    )


def _scripted_critique(security_gap: str = "missing key rotation policy") -> ScriptedResponse:
    payload = {
        "missing_components": [],
        "weak_data_flows": ["Audit fan-out missing"],
        "security_gaps": [security_gap],
        "deployment_gaps": [],
        "confidence": 0.78,
    }
    return ScriptedResponse(
        text=json.dumps(payload),
        usage=TokenUsage(input_tokens=300, output_tokens=120),
        cost_usd=0.00045,
        model="fake/small",
        provider="fake",
    )


@pytest.mark.asyncio
async def test_solution_design_agent_runs_flagship_then_small_critique() -> None:
    """Two turns; first uses flagship tier, second uses small tier; cost rolls up."""
    fake = FakeLLMClient([_scripted_draft(), _scripted_critique()])
    payload = _sample_input()

    hld = await run_solution_design_agent(payload, client=fake)

    fake.assert_called(2)
    assert fake.calls[0].tier == "flagship"
    assert fake.calls[0].node_name == "solution_design.draft"
    assert fake.calls[1].tier == "small"
    assert fake.calls[1].node_name == "solution_design.critique"
    # Both turns share the bid trace_id.
    assert fake.calls[0].trace_id == str(payload.bid_id)
    assert fake.calls[1].trace_id == str(payload.bid_id)
    # Cost is summed across both turns.
    assert hld.llm_cost_usd == pytest.approx(0.0021 + 0.00045, abs=1e-6)
    assert hld.llm_tier_used == "flagship+small"


@pytest.mark.asyncio
async def test_solution_design_agent_carries_dropped_sa_integrations() -> None:
    """Wrapper enforces: every SA integration must show up in integration_points."""
    fake = FakeLLMClient([_scripted_draft(), _scripted_critique()])
    hld = await run_solution_design_agent(_sample_input(), client=fake)

    assert "Notification bus" in hld.integration_points
    # Existing entries preserved without dedupe corruption.
    assert hld.integration_points.count("Identity provider") == 1


@pytest.mark.asyncio
async def test_solution_design_agent_strips_dangling_component_dependencies() -> None:
    fake = FakeLLMClient([_scripted_draft(), _scripted_critique()])
    hld = await run_solution_design_agent(_sample_input(), client=fake)

    pg = next(c for c in hld.components if c.name == "Postgres Cluster")
    assert "GHOST" not in pg.depends_on
    assert pg.depends_on == ["FastAPI Service"]


@pytest.mark.asyncio
async def test_solution_design_agent_appends_critique_security_and_data_flow_notes() -> None:
    """Critique findings get merged into the draft so reviewers see them in the artifact."""
    fake = FakeLLMClient([_scripted_draft(), _scripted_critique("rotate KMS keys quarterly")])
    hld = await run_solution_design_agent(_sample_input(), client=fake)

    assert "rotate KMS keys quarterly" in hld.security_approach
    assert any("Audit fan-out missing" in flow for flow in hld.data_flows)


@pytest.mark.asyncio
async def test_solution_design_agent_tolerates_critique_parse_failure() -> None:
    """Bad critique JSON is non-fatal — wrapper proceeds with the unmodified draft."""
    fake = FakeLLMClient([_scripted_draft(), ScriptedResponse(text="not JSON")])
    hld = await run_solution_design_agent(_sample_input(), client=fake)

    assert len(hld.components) == 3
    # No critique-flagged data flow note (critique was unparseable, defaults applied).
    assert all("critique-flagged" not in flow for flow in hld.data_flows)


@pytest.mark.asyncio
async def test_solution_design_agent_raises_on_empty_components() -> None:
    """Empty components = useless artifact; raise so the activity picks the stub."""
    bad_draft = ScriptedResponse(
        text=json.dumps(
            {
                "architecture_overview": "x",
                "components": [],
                "data_flows": [],
                "integration_points": [],
                "security_approach": "x",
                "deployment_model": "x",
            }
        )
    )
    # critique never reached
    fake = FakeLLMClient([bad_draft, _scripted_critique()])
    with pytest.raises(Exception):
        await run_solution_design_agent(_sample_input(), client=fake)


@pytest.mark.asyncio
async def test_solution_design_agent_raises_on_garbage_draft() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="not even close"), _scripted_critique()])
    with pytest.raises(Exception):
        await run_solution_design_agent(_sample_input(), client=fake)
