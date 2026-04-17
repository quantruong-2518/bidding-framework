"""Unit tests for the Domain LangGraph agent — mock LLM + KB, verify graph flow + loop cap."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents import domain_agent
from tools.claude_client import HAIKU, SONNET, ClaudeResponse
from workflows.artifacts import DomainNotes, StreamInput
from workflows.models import RequirementAtom


def _sample_input() -> StreamInput:
    return StreamInput(
        bid_id=uuid4(),
        client_name="Acme Bank",
        industry="banking",
        region="APAC",
        requirements=[
            RequirementAtom(
                id="REQ-001",
                text="Must comply with PCI DSS",
                category="compliance",
            ),
            RequirementAtom(
                id="REQ-002",
                text="Data residency in-region for APAC customers",
                category="compliance",
            ),
            RequirementAtom(
                id="REQ-003",
                text="Support for Bahasa Indonesia and Vietnamese",
                category="functional",
            ),
        ],
        constraints=["Budget capped at 500 MD"],
        deadline=datetime.now(timezone.utc) + timedelta(days=45),
    )


def _tag_response() -> ClaudeResponse:
    tags = [
        {"id": "REQ-001", "domain_tags": ["compliance"], "compliance_hint": "PCI DSS", "notes": "card data"},
        {"id": "REQ-002", "domain_tags": ["data_residency"], "compliance_hint": "", "notes": "APAC residency"},
        {"id": "REQ-003", "domain_tags": ["accessibility", "terminology"], "compliance_hint": "", "notes": "i18n"},
    ]
    return ClaudeResponse(text=json.dumps(tags), model=HAIKU, usage={"input_tokens": 10})


def _synthesis_response(confidence: float = 0.75) -> ClaudeResponse:
    payload = {
        "compliance": [
            {
                "framework": "PCI DSS",
                "requirement": "Cardholder data encrypted at rest and in transit.",
                "applies": True,
                "notes": "Applies because of REQ-001.",
            },
            {
                "framework": "APAC data residency",
                "requirement": "Customer data stored in-region.",
                "applies": True,
            },
        ],
        "best_practices": [
            {
                "title": "Tokenisation at entry",
                "description": "Tokenise PAN at the edge to minimise CDE scope.",
            },
            {
                "title": "Bilingual UX",
                "description": "Bahasa/Vietnamese localisation via ICU message format.",
            },
        ],
        "industry_constraints": [
            "APAC change-window restrictions (Sunday 02:00-06:00 local).",
        ],
        "glossary": {
            "CDE": "Cardholder Data Environment",
            "PAN": "Primary Account Number",
            "ROC": "Report on Compliance",
        },
        "confidence": confidence,
        "sources": ["kb/compliance/banking-apac.md"],
    }
    return ClaudeResponse(text=json.dumps(payload), model=SONNET, usage={"input_tokens": 20})


def _critique_response(confidence: float = 0.82) -> ClaudeResponse:
    return ClaudeResponse(
        text=json.dumps(
            {"coverage_gaps": [], "quality_issues": [], "confidence": confidence}
        ),
        model=SONNET,
    )


def _kb_hits() -> list[dict[str, object]]:
    return [
        {
            "content": "APAC banking compliance overview — PCI DSS 4.0, local residency.",
            "score": 0.77,
            "source_path": "kb/compliance/banking-apac.md",
            "metadata": {"domain": "banking"},
        }
    ]


@pytest.mark.asyncio
async def test_run_domain_agent_happy_path_populates_draft() -> None:
    kb_mock = AsyncMock(return_value=_kb_hits())
    generate_mock = AsyncMock(
        side_effect=[
            _tag_response(),
            _synthesis_response(confidence=0.75),
            _critique_response(confidence=0.82),
        ]
    )

    with (
        patch("agents.domain_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        notes = await domain_agent.run_domain_agent(_sample_input())

    assert isinstance(notes, DomainNotes)
    assert any(c.framework == "PCI DSS" for c in notes.compliance)
    assert len(notes.best_practices) >= 2
    assert "CDE" in notes.glossary
    assert notes.confidence >= 0.75
    assert "kb/compliance/banking-apac.md" in notes.sources
    assert generate_mock.await_count == 3


@pytest.mark.asyncio
async def test_run_domain_agent_loops_once_when_confidence_low() -> None:
    kb_mock = AsyncMock(return_value=_kb_hits())
    generate_mock = AsyncMock(
        side_effect=[
            _tag_response(),
            _synthesis_response(confidence=0.3),
            _critique_response(confidence=0.2),
            _synthesis_response(confidence=0.6),
            _critique_response(confidence=0.7),
        ]
    )

    with (
        patch("agents.domain_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        notes = await domain_agent.run_domain_agent(_sample_input())

    assert generate_mock.await_count == 5
    assert notes.confidence >= 0.6


@pytest.mark.asyncio
async def test_run_domain_agent_degrades_when_kb_unavailable() -> None:
    kb_mock = AsyncMock(return_value=[])
    generate_mock = AsyncMock(
        side_effect=[
            _tag_response(),
            _synthesis_response(confidence=0.4),
            _critique_response(confidence=0.4),
        ]
    )

    with (
        patch("agents.domain_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        notes = await domain_agent.run_domain_agent(_sample_input())

    assert notes.compliance
    assert generate_mock.await_count == 3
