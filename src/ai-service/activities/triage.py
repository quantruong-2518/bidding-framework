"""S1 Triage activity — compute multi-criteria score and BID/NO_BID recommendation."""

from __future__ import annotations

import logging

from temporalio import activity

from agents import triage_agent
from workflows.models import BidCard, TriageDecision

logger = logging.getLogger(__name__)

BID_THRESHOLD: float = 60.0


def _overall(breakdown: dict[str, float]) -> float:
    if not breakdown:
        return 0.0
    return round(sum(breakdown.values()) / len(breakdown), 2)


def _rationale(overall: float, breakdown: dict[str, float]) -> str:
    top = max(breakdown.items(), key=lambda kv: kv[1])
    bottom = min(breakdown.items(), key=lambda kv: kv[1])
    verdict = "BID" if overall >= BID_THRESHOLD else "NO_BID"
    return (
        f"Overall {overall:.1f} -> {verdict}. Strongest: {top[0]} ({top[1]:.1f}); "
        f"weakest: {bottom[0]} ({bottom[1]:.1f})."
    )


@activity.defn(name="triage_activity")
async def triage_activity(bid_card: BidCard) -> TriageDecision:
    """Score the bid card and emit a triage recommendation."""
    activity.logger.info("triage.start bid_id=%s", bid_card.bid_id)

    breakdown = triage_agent.score(bid_card)
    overall = _overall(breakdown)
    recommendation = "BID" if overall >= BID_THRESHOLD else "NO_BID"
    decision = TriageDecision(
        score_breakdown=breakdown,
        overall_score=overall,
        recommendation=recommendation,
        rationale=_rationale(overall, breakdown),
    )
    activity.logger.info(
        "triage.done bid_id=%s overall=%.2f rec=%s", bid_card.bid_id, overall, recommendation
    )
    return decision
