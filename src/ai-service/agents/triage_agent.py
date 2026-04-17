"""Triage scoring stub — deterministic heuristics swapped for a LangGraph/Haiku graph in Task 1.3."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workflows.models import BidCard

logger = logging.getLogger(__name__)

CRITERIA: tuple[str, ...] = (
    "win_probability",
    "resource_availability",
    "technical_fit",
    "strategic_value",
    "timeline_feasibility",
)

_STRATEGIC_INDUSTRIES = {"banking", "finance", "healthcare", "insurance", "government"}
_STRONG_TECH_KEYWORDS = {
    "microservices",
    "kubernetes",
    "cloud",
    "aws",
    "azure",
    "gcp",
    "ai",
    "ml",
    "data",
    "analytics",
    "api",
}


def _hash_unit(seed: str, salt: str) -> float:
    """Deterministic 0..1 value derived from bid identity; removed once LLM wiring lands."""
    digest = hashlib.sha256(f"{seed}:{salt}".encode()).digest()
    return digest[0] / 255.0


def score(bid_card: "BidCard") -> dict[str, float]:
    """Return a score 0..100 per criterion. Deterministic stub — replace in Task 1.3."""
    seed = f"{bid_card.bid_id}|{bid_card.client_name}"
    keywords_lc = {k.lower() for k in bid_card.technology_keywords}

    tech_hits = len(keywords_lc & _STRONG_TECH_KEYWORDS)
    technical_fit = min(100.0, 40.0 + tech_hits * 15.0 + _hash_unit(seed, "tech") * 10.0)

    strategic_value = (
        80.0 if bid_card.industry.strip().lower() in _STRATEGIC_INDUSTRIES else 45.0
    ) + _hash_unit(seed, "strategy") * 10.0
    strategic_value = min(100.0, strategic_value)

    profile_bonus = {"S": 80.0, "M": 70.0, "L": 55.0, "XL": 40.0}[bid_card.estimated_profile]
    timeline_feasibility = min(100.0, profile_bonus + _hash_unit(seed, "timeline") * 10.0)

    win_probability = min(100.0, 50.0 + tech_hits * 8.0 + _hash_unit(seed, "win") * 15.0)
    resource_availability = min(
        100.0, 60.0 - (len(bid_card.requirements_raw) * 0.5) + _hash_unit(seed, "res") * 20.0
    )
    resource_availability = max(0.0, resource_availability)

    breakdown = {
        "win_probability": round(win_probability, 2),
        "resource_availability": round(resource_availability, 2),
        "technical_fit": round(technical_fit, 2),
        "strategic_value": round(strategic_value, 2),
        "timeline_feasibility": round(timeline_feasibility, 2),
    }
    logger.debug("triage.score bid_id=%s breakdown=%s", bid_card.bid_id, breakdown)
    return breakdown
