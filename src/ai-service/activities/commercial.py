"""S7 Commercial Strategy activity — Temporal wrapper around the pricing agent.

Falls back to the Phase 2.1 deterministic stub when no LLM provider is
available (``is_llm_available()``) or when the LLM produces unparseable
output. The wrapper, not the agent, is responsible for the fallback so
``PricingDraft`` consumers always see a well-formed artifact.
"""

from __future__ import annotations

import logging

from temporalio import activity

from agents.commercial_agent import _BLENDED_DAY_RATE_USD, run_commercial_agent
from config.llm import is_llm_available
from tools.langfuse_client import get_tracer, span_context as langfuse_span_context
from workflows.artifacts import CommercialInput, PricingDraft, PricingLine

logger = logging.getLogger(__name__)


def _commercial_stub(payload: CommercialInput) -> PricingDraft:
    """Phase 2.1 deterministic baseline — preserved as the fallback contract."""
    labour_cost = round(payload.wbs.total_effort_md * _BLENDED_DAY_RATE_USD, 2)
    contingency = round(labour_cost * 0.10, 2)
    travel_estimate = round(labour_cost * 0.03, 2)
    lines = [
        PricingLine(label="Labour (blended day rate)", amount=labour_cost, unit="USD"),
        PricingLine(label="Contingency (10%)", amount=contingency, unit="USD"),
        PricingLine(label="Travel + expenses (est.)", amount=travel_estimate, unit="USD"),
    ]
    subtotal = round(sum(line.amount for line in lines), 2)
    margin_pct = 18.0 if payload.industry.lower() in {"banking", "insurance"} else 15.0
    total = round(subtotal * (1 + margin_pct / 100.0), 2)
    scenarios = {
        "aggressive": round(total * 0.92, 2),
        "baseline": total,
        "conservative": round(total * 1.08, 2),
    }
    return PricingDraft(
        bid_id=payload.bid_id,
        model="fixed_price",
        currency="USD",
        lines=lines,
        subtotal=subtotal,
        margin_pct=margin_pct,
        total=total,
        scenarios=scenarios,
        notes="Advisory only — commercial team adjusts before S8 assembly.",
    )


@activity.defn(name="commercial_activity")
async def commercial_activity(payload: CommercialInput) -> PricingDraft:
    """Derive an advisory pricing model from the WBS + industry context."""
    if not is_llm_available():
        activity.logger.info("commercial.fallback_to_stub bid_id=%s", payload.bid_id)
        return _commercial_stub(payload)

    activity.logger.info(
        "commercial.start bid_id=%s effort_md=%.1f industry=%s",
        payload.bid_id,
        payload.wbs.total_effort_md,
        payload.industry,
    )
    activity.heartbeat("commercial_started")

    tracer = get_tracer()
    span = tracer.start_span(
        trace_id=str(payload.bid_id),
        name="commercial",
        metadata={"attempt": activity.info().attempt, "tier": "nano"},
    )
    try:
        async with langfuse_span_context(span):
            draft = await run_commercial_agent(payload)
    except Exception as exc:  # noqa: BLE001 — any agent failure → stub fallback
        activity.logger.warning(
            "commercial.agent_failed_using_stub bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        draft = _commercial_stub(payload)
    finally:
        span.end()
        await tracer.aclose()

    activity.heartbeat("commercial_completed")
    activity.logger.info(
        "commercial.done bid_id=%s total=%.2f margin=%.1f%% lines=%d cost_usd=%.6f",
        payload.bid_id,
        draft.total,
        draft.margin_pct,
        len(draft.lines),
        draft.llm_cost_usd or 0.0,
    )
    return draft
