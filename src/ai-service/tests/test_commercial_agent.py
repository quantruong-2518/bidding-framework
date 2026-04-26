"""Conv 14 — S7 Commercial real LLM via nano tier; FakeLLMClient covers parse + arithmetic."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.commercial_agent import run_commercial_agent
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.artifacts import (
    CommercialInput,
    PricingLine,
    WBSDraft,
    WBSItem,
)


def _sample_input(industry: str = "banking") -> CommercialInput:
    return CommercialInput(
        bid_id=uuid4(),
        industry=industry,
        wbs=WBSDraft(
            bid_id=uuid4(),
            items=[
                WBSItem(id="WBS-100", name="Discovery", effort_md=20.0),
                WBSItem(id="WBS-300", name="Build", effort_md=60.0),
                WBSItem(id="WBS-500", name="Test", effort_md=20.0),
            ],
            total_effort_md=100.0,
            timeline_weeks=10,
            critical_path=["WBS-300", "WBS-500"],
        ),
    )


def _scripted_pricing(margin_pct: float = 17.5) -> ScriptedResponse:
    payload = {
        "model": "fixed_price",
        "currency": "USD",
        "lines": [
            {"label": "Labour (blended day rate)", "amount": 90000.0, "unit": "USD"},
            {"label": "Contingency (12%)", "amount": 10800.0, "unit": "USD"},
            {"label": "Travel + expenses", "amount": 2700.0, "unit": "USD"},
        ],
        "margin_pct": margin_pct,
        "notes": "Banking compliance overhead lifts margin to upper-band.",
    }
    return ScriptedResponse(
        text=json.dumps(payload),
        usage=TokenUsage(input_tokens=200, output_tokens=80),
        cost_usd=0.000345,
        model="fake/nano",
        provider="fake",
    )


@pytest.mark.asyncio
async def test_commercial_agent_finalises_arithmetic_from_llm_lines() -> None:
    """Wrapper sums LLM-returned lines, applies margin %, derives scenarios."""
    fake = FakeLLMClient(_scripted_pricing(margin_pct=18.0))
    payload = _sample_input()

    draft = await run_commercial_agent(payload, client=fake)

    # Arithmetic is wrapper-side, not LLM-side.
    assert draft.subtotal == 90000.0 + 10800.0 + 2700.0
    assert draft.subtotal == 103500.0
    assert draft.margin_pct == 18.0
    assert draft.total == round(103500.0 * 1.18, 2)
    assert draft.scenarios["baseline"] == draft.total
    assert draft.scenarios["aggressive"] == round(draft.total * 0.92, 2)
    assert draft.scenarios["conservative"] == round(draft.total * 1.08, 2)
    # LLM cost + tier propagated to the artifact for the dashboard.
    assert draft.llm_tier_used == "nano"
    assert draft.llm_cost_usd == pytest.approx(0.000345, rel=0, abs=1e-6)


@pytest.mark.asyncio
async def test_commercial_agent_uses_nano_tier_and_propagates_trace_id() -> None:
    """nano default + trace_id wiring so Langfuse links spans to the bid."""
    fake = FakeLLMClient(_scripted_pricing())
    payload = _sample_input()

    await run_commercial_agent(payload, client=fake)

    fake.assert_called(1)
    request = fake.calls[0]
    assert request.tier == "nano"
    assert request.trace_id == str(payload.bid_id)
    assert request.node_name == "commercial_agent.pricing"


@pytest.mark.asyncio
async def test_commercial_agent_strips_markdown_fences_around_json() -> None:
    """Defensive: nano models sometimes wrap JSON in ```json``` fences."""
    fenced = ScriptedResponse(
        text="```json\n"
        + json.dumps(
            {
                "model": "fixed_price",
                "currency": "USD",
                "lines": [{"label": "Labour", "amount": 50000.0, "unit": "USD"}],
                "margin_pct": 15.0,
                "notes": "fenced",
            }
        )
        + "\n```",
        usage=TokenUsage(input_tokens=100, output_tokens=40),
    )
    fake = FakeLLMClient(fenced)
    draft = await run_commercial_agent(_sample_input(), client=fake)
    assert draft.subtotal == 50000.0
    assert draft.notes == "fenced"


@pytest.mark.asyncio
async def test_commercial_agent_raises_on_empty_lines_for_stub_fallback() -> None:
    """Empty pricing lines = useless artifact; raise so the activity picks the stub."""
    bad = ScriptedResponse(
        text=json.dumps(
            {
                "model": "fixed_price",
                "currency": "USD",
                "lines": [],
                "margin_pct": 12.0,
                "notes": "x",
            }
        )
    )
    fake = FakeLLMClient(bad)
    with pytest.raises(ValueError, match="empty pricing lines"):
        await run_commercial_agent(_sample_input(), client=fake)


@pytest.mark.asyncio
async def test_commercial_agent_raises_on_unparseable_json() -> None:
    """Garbage in → ValidationError out; activity wrapper catches and falls back."""
    bad = ScriptedResponse(text="not even close to JSON")
    fake = FakeLLMClient(bad)
    with pytest.raises(Exception):
        await run_commercial_agent(_sample_input(), client=fake)


@pytest.mark.asyncio
async def test_commercial_agent_coerces_unknown_pricing_model_to_fixed_price() -> None:
    """LLM may invent a model name; coerce to the Literal-accepted default."""
    weird = ScriptedResponse(
        text=json.dumps(
            {
                "model": "bespoke",
                "currency": "USD",
                "lines": [
                    {"label": "Labour", "amount": 50000.0, "unit": "USD"},
                    {"label": "Contingency", "amount": 5000.0, "unit": "USD"},
                ],
                "margin_pct": 15.0,
                "notes": "n",
            }
        )
    )
    fake = FakeLLMClient(weird)
    draft = await run_commercial_agent(_sample_input(), client=fake)
    assert draft.model == "fixed_price"


@pytest.mark.asyncio
async def test_commercial_agent_respects_industry_neutral_margin() -> None:
    """Wrapper does NOT override margin_pct; LLM is the source of truth here."""
    fake = FakeLLMClient(_scripted_pricing(margin_pct=12.0))
    draft = await run_commercial_agent(_sample_input(industry="retail"), client=fake)
    assert draft.margin_pct == 12.0
