"""Unit tests for the SA LangGraph agent — mock LLM + KB, verify graph flow + loop cap."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents import sa_agent
from tools.claude_client import HAIKU, SONNET, ClaudeResponse
from workflows.artifacts import SolutionArchitectureDraft, StreamInput
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
                text="The system shall expose a REST API for account lookup",
                category="functional",
            ),
            RequirementAtom(
                id="REQ-002",
                text="API p95 latency must be under 200ms",
                category="nfr",
            ),
            RequirementAtom(
                id="REQ-003",
                text="Must comply with PCI DSS",
                category="compliance",
            ),
        ],
        constraints=["Budget capped at 500 MD"],
        deadline=datetime.now(timezone.utc) + timedelta(days=45),
    )


def _classify_response() -> ClaudeResponse:
    signals = [
        {"id": "REQ-001", "signals": ["api"], "notes": "REST API exposure"},
        {"id": "REQ-002", "signals": ["performance"], "notes": "p95 latency NFR"},
        {"id": "REQ-003", "signals": ["compliance", "security"], "notes": "PCI DSS"},
    ]
    return ClaudeResponse(text=json.dumps(signals), model=HAIKU, usage={"input_tokens": 10})


def _synthesis_response(confidence: float = 0.75) -> ClaudeResponse:
    payload = {
        "tech_stack": [
            {"layer": "API", "choice": "NestJS REST", "rationale": "Matches REST ask."},
            {"layer": "Datastore", "choice": "PostgreSQL 16", "rationale": "ACID + compliance."},
            {"layer": "Cache", "choice": "Redis 7", "rationale": "Sub-200ms latency budget."},
            {"layer": "Runtime", "choice": "Kubernetes", "rationale": "Elasticity + blue/green."},
        ],
        "architecture_patterns": [
            {
                "name": "Network segmentation",
                "description": "CDE isolated from corporate network per PCI DSS.",
                "applies_to": ["REQ-003"],
            },
            {
                "name": "Edge API gateway",
                "description": "Rate limiting + auth at edge.",
                "applies_to": ["REQ-001"],
            },
        ],
        "nfr_targets": {
            "availability": "99.9% monthly",
            "p95_latency_ms": "200",
            "rto_minutes": "30",
            "rpo_minutes": "5",
        },
        "technical_risks": [
            {
                "title": "Core banking latency",
                "likelihood": "MEDIUM",
                "impact": "HIGH",
                "mitigation": "Benchmark mainframe adapter in week 1.",
            }
        ],
        "integrations": ["Core banking (mainframe)", "Identity (SSO)"],
        "confidence": confidence,
        "sources": ["kb/patterns/banking-api-gateway.md"],
    }
    return ClaudeResponse(text=json.dumps(payload), model=SONNET, usage={"input_tokens": 20})


def _critique_response(confidence: float = 0.82) -> ClaudeResponse:
    payload = {
        "coverage_gaps": [],
        "quality_issues": [],
        "confidence": confidence,
    }
    return ClaudeResponse(text=json.dumps(payload), model=SONNET)


def _kb_hits() -> list[dict[str, object]]:
    return [
        {
            "content": "Banking API gateway reference — auth, rate limit, segmentation.",
            "score": 0.78,
            "source_path": "kb/patterns/banking-api-gateway.md",
            "metadata": {"domain": "banking"},
        }
    ]


@pytest.mark.asyncio
async def test_run_sa_agent_happy_path_populates_draft() -> None:
    kb_mock = AsyncMock(return_value=_kb_hits())
    generate_mock = AsyncMock(
        side_effect=[
            _classify_response(),
            _synthesis_response(confidence=0.75),
            _critique_response(confidence=0.82),
        ]
    )

    with (
        patch("agents.sa_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await sa_agent.run_sa_agent(_sample_input())

    assert isinstance(draft, SolutionArchitectureDraft)
    assert {c.layer for c in draft.tech_stack} >= {"API", "Datastore"}
    assert len(draft.architecture_patterns) >= 2
    assert draft.nfr_targets.get("p95_latency_ms") == "200"
    assert draft.technical_risks and draft.technical_risks[0].impact == "HIGH"
    assert draft.confidence >= 0.75
    assert "kb/patterns/banking-api-gateway.md" in draft.sources
    assert generate_mock.await_count == 3


@pytest.mark.asyncio
async def test_run_sa_agent_loops_once_when_confidence_low() -> None:
    kb_mock = AsyncMock(return_value=_kb_hits())
    generate_mock = AsyncMock(
        side_effect=[
            _classify_response(),
            _synthesis_response(confidence=0.3),
            _critique_response(confidence=0.2),
            _synthesis_response(confidence=0.6),
            _critique_response(confidence=0.7),
        ]
    )

    with (
        patch("agents.sa_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await sa_agent.run_sa_agent(_sample_input())

    assert generate_mock.await_count == 5
    assert draft.confidence >= 0.6


@pytest.mark.asyncio
async def test_run_sa_agent_degrades_when_kb_unavailable() -> None:
    kb_mock = AsyncMock(return_value=[])
    generate_mock = AsyncMock(
        side_effect=[
            _classify_response(),
            _synthesis_response(confidence=0.4),
            _critique_response(confidence=0.4),
        ]
    )

    with (
        patch("agents.sa_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await sa_agent.run_sa_agent(_sample_input())

    assert draft.tech_stack
    assert generate_mock.await_count == 3
