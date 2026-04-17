"""Unit tests for the BA LangGraph agent — mock LLM + KB, verify graph flow + loop cap."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents import ba_agent
from agents.models import BARequirements, BusinessRequirementsDraft
from tools.claude_client import HAIKU, SONNET, ClaudeResponse
from workflows.models import RequirementAtom


def _sample_input() -> BARequirements:
    return BARequirements(
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


def _extract_response() -> ClaudeResponse:
    atoms = [
        {
            "id": "REQ-001",
            "title": "Account lookup REST API",
            "category": "functional",
            "priority": "MUST",
            "summary": "Expose REST API for account lookup.",
        },
        {
            "id": "REQ-002",
            "title": "API latency <200ms p95",
            "category": "nfr",
            "priority": "MUST",
            "summary": "Sub-200ms p95 latency.",
        },
        {
            "id": "REQ-003",
            "title": "PCI DSS compliance",
            "category": "compliance",
            "priority": "MUST",
            "summary": "Must comply with PCI DSS.",
        },
    ]
    return ClaudeResponse(text=json.dumps(atoms), model=HAIKU, usage={"input_tokens": 10})


def _synthesis_response(confidence: float = 0.75) -> ClaudeResponse:
    payload = {
        "executive_summary": "Deliver a secure banking API.",
        "business_objectives": ["Increase digital self-service"],
        "scope": {
            "in_scope": ["Account lookup API"],
            "out_of_scope": ["Loan origination"],
        },
        "functional_requirements": [
            {
                "id": "REQ-001",
                "title": "Account lookup REST API",
                "description": "Expose a REST API for account lookup.",
                "priority": "MUST",
                "rationale": "Core ask of the RFP.",
            },
            {
                "id": "REQ-002",
                "title": "Latency budget",
                "description": "API p95 latency under 200ms.",
                "priority": "MUST",
                "rationale": "Client NFR.",
            },
            {
                "id": "REQ-003",
                "title": "PCI DSS",
                "description": "Must comply with PCI DSS.",
                "priority": "MUST",
                "rationale": "Regulatory obligation.",
            },
        ],
        "assumptions": ["Existing core banking APIs can be reused"],
        "constraints": ["Budget capped at 500 MD"],
        "success_criteria": ["<200ms p95 latency", "PCI DSS ROC issued"],
        "risks": [
            {
                "title": "Legacy integration complexity",
                "likelihood": "MEDIUM",
                "impact": "HIGH",
                "mitigation": "Spike in week 1 to de-risk mainframe adapter.",
            }
        ],
        "similar_projects": [
            {
                "project_id": "project-acme-core-2023",
                "relevance_score": 0.81,
                "why_relevant": "Same client, banking core modernisation.",
            }
        ],
        "confidence": confidence,
        "sources": ["kb/projects/project-acme-core-2023.md"],
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
            "content": "Acme core banking modernisation delivered 2023 — 12 month runway.",
            "score": 0.81,
            "source_path": "kb/projects/project-acme-core-2023.md",
            "metadata": {"client": "Acme Bank", "domain": "banking"},
        }
    ]


@pytest.mark.asyncio
async def test_run_ba_agent_happy_path_populates_draft() -> None:
    """Mocked Haiku + Sonnet produce a populated BusinessRequirementsDraft in one loop."""
    kb_mock = AsyncMock(return_value=_kb_hits())
    generate_mock = AsyncMock(
        side_effect=[
            _extract_response(),
            _synthesis_response(confidence=0.75),
            _critique_response(confidence=0.82),
        ]
    )

    with (
        patch("agents.ba_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await ba_agent.run_ba_agent(_sample_input())

    assert isinstance(draft, BusinessRequirementsDraft)
    assert draft.executive_summary
    assert len(draft.functional_requirements) == 3
    assert {fr.id for fr in draft.functional_requirements} == {"REQ-001", "REQ-002", "REQ-003"}
    assert draft.risks and draft.risks[0].likelihood == "MEDIUM"
    assert draft.similar_projects and draft.similar_projects[0].project_id
    assert draft.confidence >= 0.75
    assert "kb/projects/project-acme-core-2023.md" in draft.sources

    kb_mock.assert_awaited_once()
    query_arg = kb_mock.await_args.kwargs.get("query") or kb_mock.await_args.args[0]
    assert "Acme Bank" in query_arg
    assert "banking" in query_arg
    assert generate_mock.await_count == 3


@pytest.mark.asyncio
async def test_run_ba_agent_loops_once_when_confidence_low() -> None:
    """Low critique confidence triggers a single resynthesis, respecting the loop cap."""
    kb_mock = AsyncMock(return_value=_kb_hits())
    # Sequence: extract, synth#1, critique#1 (low), synth#2, critique#2 (high).
    generate_mock = AsyncMock(
        side_effect=[
            _extract_response(),
            _synthesis_response(confidence=0.3),
            _critique_response(confidence=0.2),
            _synthesis_response(confidence=0.6),
            _critique_response(confidence=0.7),
        ]
    )

    with (
        patch("agents.ba_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await ba_agent.run_ba_agent(_sample_input())

    # Extract + 2x synthesize + 2x critique = 5 LLM calls; loop capped at MAX_ITERATIONS.
    assert generate_mock.await_count == 5
    assert draft.confidence >= 0.6


@pytest.mark.asyncio
async def test_run_ba_agent_degrades_when_kb_unavailable() -> None:
    """Empty KB results still produce a draft — agent must not crash on RAG outages."""
    kb_mock = AsyncMock(return_value=[])
    generate_mock = AsyncMock(
        side_effect=[
            _extract_response(),
            _synthesis_response(confidence=0.4),
            _critique_response(confidence=0.4),
        ]
    )

    with (
        patch("agents.ba_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await ba_agent.run_ba_agent(_sample_input())

    assert draft.functional_requirements
    # similar_projects may still be populated from LLM hallucination; agent doesn't filter —
    # but we assert graph completed cleanly.
    assert generate_mock.await_count == 3
