"""Conv 14 — S6 WBS real LLM via small tier; FakeLLMClient covers parse + invariants."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.models import (
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
)
from agents.wbs_agent import run_wbs_agent
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.artifacts import HLDComponent, HLDDraft, WBSInput


def _ba_draft(must_count: int = 4) -> BusinessRequirementsDraft:
    bid_id = uuid4()
    return BusinessRequirementsDraft(
        bid_id=bid_id,
        executive_summary="Secure banking API platform.",
        business_objectives=["Increase digital self-service"],
        scope={"in_scope": ["Core API"], "out_of_scope": []},
        functional_requirements=[
            FunctionalRequirement(
                id=f"REQ-{i:03d}",
                title=f"Functional req {i}",
                description="x",
                priority="MUST" if i <= must_count else "SHOULD",
                rationale="y",
            )
            for i in range(1, 8)
        ],
        assumptions=[],
        constraints=[],
        success_criteria=[],
        risks=[
            RiskItem(
                title="Vendor dependency", likelihood="MEDIUM", impact="HIGH", mitigation="x"
            )
        ],
        similar_projects=[],
        confidence=0.7,
        sources=[],
    )


def _hld_draft() -> HLDDraft:
    return HLDDraft(
        bid_id=uuid4(),
        architecture_overview="Layered banking API.",
        components=[HLDComponent(name="API Gateway", responsibility="ingress")],
        integration_points=["Identity provider", "Core ledger", "Notification bus"],
        deployment_model="K8s rolling",
    )


def _scripted_wbs() -> ScriptedResponse:
    payload = {
        "items": [
            {"id": "WBS-000", "name": "Initiation", "parent_id": None,
             "effort_md": 12.0, "owner_role": "pm", "depends_on": []},
            {"id": "WBS-100", "name": "Discovery", "parent_id": None,
             "effort_md": 24.0, "owner_role": "ba", "depends_on": ["WBS-000"]},
            {"id": "WBS-300", "name": "Build", "parent_id": None,
             "effort_md": 96.0, "owner_role": "pm",
             "depends_on": ["WBS-100", "WBS-NONEXISTENT"]},
            {"id": "WBS-500", "name": "Test", "parent_id": None,
             "effort_md": 30.0, "owner_role": "qc", "depends_on": ["WBS-300"]},
        ],
        "critical_path": ["WBS-100", "WBS-300", "WBS-500", "WBS-GHOST"],
        "rationale": "Compressed to 4 phases; build effort lifted for compliance.",
    }
    return ScriptedResponse(
        text=json.dumps(payload),
        usage=TokenUsage(input_tokens=400, output_tokens=180),
        cost_usd=0.000812,
        model="fake/small",
        provider="fake",
    )


@pytest.mark.asyncio
async def test_wbs_agent_recomputes_total_and_timeline_from_items() -> None:
    """Wrapper sums effort_md, applies 20-MD/week heuristic — LLM doesn't do math."""
    fake = FakeLLMClient(_scripted_wbs())
    payload = WBSInput(bid_id=uuid4(), hld=_hld_draft(), ba_draft=_ba_draft())

    draft = await run_wbs_agent(payload, client=fake)

    assert draft.total_effort_md == 12.0 + 24.0 + 96.0 + 30.0
    assert draft.total_effort_md == 162.0
    # 162 / 20 = 8.1 -> rounds to 8; min is 4.
    assert draft.timeline_weeks == 8
    assert draft.llm_tier_used == "small"
    assert draft.llm_cost_usd == pytest.approx(0.000812, abs=1e-6)


@pytest.mark.asyncio
async def test_wbs_agent_drops_dangling_dependencies_and_critical_path_ids() -> None:
    """Defensive: LLM may invent ids; wrapper filters them out before downstream."""
    fake = FakeLLMClient(_scripted_wbs())
    payload = WBSInput(bid_id=uuid4(), hld=None, ba_draft=_ba_draft())

    draft = await run_wbs_agent(payload, client=fake)

    build_item = next(it for it in draft.items if it.id == "WBS-300")
    assert "WBS-NONEXISTENT" not in build_item.depends_on
    assert build_item.depends_on == ["WBS-100"]
    assert "WBS-GHOST" not in draft.critical_path
    assert draft.critical_path == ["WBS-100", "WBS-300", "WBS-500"]


@pytest.mark.asyncio
async def test_wbs_agent_floors_timeline_at_four_weeks() -> None:
    """A tiny-effort WBS still reports the minimum pod-week footprint."""
    tiny = ScriptedResponse(
        text=json.dumps(
            {
                "items": [
                    {"id": "WBS-000", "name": "Tiny", "parent_id": None,
                     "effort_md": 5.0, "owner_role": "pm", "depends_on": []}
                ],
                "critical_path": ["WBS-000"],
                "rationale": "MVP-fastpath",
            }
        )
    )
    fake = FakeLLMClient(tiny)
    payload = WBSInput(bid_id=uuid4(), hld=None, ba_draft=_ba_draft(must_count=1))

    draft = await run_wbs_agent(payload, client=fake)
    assert draft.timeline_weeks == 4


@pytest.mark.asyncio
async def test_wbs_agent_uses_small_tier_and_propagates_trace_id() -> None:
    fake = FakeLLMClient(_scripted_wbs())
    payload = WBSInput(bid_id=uuid4(), hld=_hld_draft(), ba_draft=_ba_draft())

    await run_wbs_agent(payload, client=fake)

    fake.assert_called(1)
    assert fake.calls[0].tier == "small"
    assert fake.calls[0].trace_id == str(payload.bid_id)
    assert fake.calls[0].node_name == "wbs_agent.synthesise"


@pytest.mark.asyncio
async def test_wbs_agent_raises_on_empty_items() -> None:
    """Empty items = useless artifact; raise so the activity picks the stub."""
    bad = ScriptedResponse(
        text=json.dumps({"items": [], "critical_path": [], "rationale": "x"})
    )
    fake = FakeLLMClient(bad)
    payload = WBSInput(bid_id=uuid4(), hld=None, ba_draft=_ba_draft())
    with pytest.raises(ValueError, match="empty WBS items"):
        await run_wbs_agent(payload, client=fake)


@pytest.mark.asyncio
async def test_wbs_agent_raises_on_garbage_json() -> None:
    fake = FakeLLMClient(ScriptedResponse(text="not even close"))
    payload = WBSInput(bid_id=uuid4(), hld=None, ba_draft=_ba_draft())
    with pytest.raises(Exception):
        await run_wbs_agent(payload, client=fake)
