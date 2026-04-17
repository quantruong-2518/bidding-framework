"""S0 Intake activity — parse RFP metadata into a structured BidCard."""

from __future__ import annotations

import logging
import re
from uuid import uuid4

from temporalio import activity

from workflows.models import BidCard, BidProfile, IntakeInput

logger = logging.getLogger(__name__)

_TECH_KEYWORD_VOCAB: tuple[str, ...] = (
    "microservices",
    "kubernetes",
    "docker",
    "cloud",
    "aws",
    "azure",
    "gcp",
    "react",
    "angular",
    "vue",
    "node",
    "python",
    "java",
    "kotlin",
    "golang",
    "ai",
    "ml",
    "nlp",
    "llm",
    "rag",
    "data",
    "analytics",
    "etl",
    "api",
    "rest",
    "graphql",
    "grpc",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "kafka",
    "oauth",
    "saml",
    "sso",
    "hipaa",
    "pci",
    "gdpr",
    "iso27001",
)

_BULLET_RE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+(.+)$")


def _estimate_profile(text_len: int) -> BidProfile:
    if text_len < 500:
        return "S"
    if text_len < 2000:
        return "M"
    if text_len < 8000:
        return "L"
    return "XL"


def _extract_keywords(text: str) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    seen: set[str] = set()
    for kw in _TECH_KEYWORD_VOCAB:
        if kw in lower and kw not in seen:
            hits.append(kw)
            seen.add(kw)
    return hits


def _extract_requirements(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        match = _BULLET_RE.match(line)
        if match:
            items.append(match.group(1).strip())
    if not items:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        items = sentences[:25]
    return items


def _scope_summary(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:280]


@activity.defn(name="intake_activity")
async def intake_activity(payload: IntakeInput) -> BidCard:
    """Extract bid-card metadata heuristically; Claude Haiku wiring lands in Task 1.3."""
    activity.logger.info("intake.start client=%s", payload.client_name)

    card = BidCard(
        bid_id=uuid4(),
        client_name=payload.client_name,
        industry=payload.industry,
        region=payload.region,
        deadline=payload.deadline,
        scope_summary=_scope_summary(payload.rfp_text),
        technology_keywords=_extract_keywords(payload.rfp_text),
        estimated_profile=_estimate_profile(len(payload.rfp_text)),
        requirements_raw=_extract_requirements(payload.rfp_text),
    )
    activity.logger.info(
        "intake.done bid_id=%s profile=%s reqs=%d",
        card.bid_id,
        card.estimated_profile,
        len(card.requirements_raw),
    )
    return card
