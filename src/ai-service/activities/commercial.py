"""S7 Commercial Strategy activity (Phase 2.1 stub)."""

from __future__ import annotations

import logging

from temporalio import activity

from workflows.artifacts import CommercialInput, PricingDraft, PricingLine

logger = logging.getLogger(__name__)

_BLENDED_DAY_RATE_USD = 900.0  # stub blended rate; real model reads from KB in Phase 3


@activity.defn(name="commercial_activity")
async def commercial_activity(payload: CommercialInput) -> PricingDraft:
    """Derive an advisory fixed-price model from the WBS totals."""
    activity.logger.info("commercial.start bid_id=%s", payload.bid_id)

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

    draft = PricingDraft(
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
    activity.logger.info(
        "commercial.done bid_id=%s total=%.2f margin=%.1f%%",
        payload.bid_id,
        total,
        margin_pct,
    )
    return draft
