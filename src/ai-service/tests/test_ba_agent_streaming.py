"""Phase 2.5 — BA / SA / Domain agents route through generate_stream when bound.

Covers for each of the three agents:
  (a) Publisher bound via stream_context → generate_stream called, tokens
      published per node (extract/classify/tag + synth + critique), final
      ClaudeResponse still JSON-parseable.
  (b) No publisher → falls through to generate() (legacy unit-test path).

Symmetric tests for SA + Domain catch node_name typos or publisher-lifecycle
drift if the three wrappers evolve independently.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import AsyncIterator, Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents import ba_agent, domain_agent, sa_agent
from agents.stream_publisher import TokenPublisher, stream_context
from tools.claude_client import HAIKU, SONNET, ClaudeResponse
from workflows.artifacts import StreamInput
from workflows.models import RequirementAtom


def _sample_input() -> StreamInput:
    return StreamInput(
        bid_id=uuid4(),
        client_name="Acme Bank",
        industry="banking",
        region="APAC",
        tenant_id="acme-bank",
        requirements=[
            RequirementAtom(
                id="REQ-001",
                text="The system shall expose a REST API for account lookup",
                category="functional",
            ),
        ],
        constraints=[],
        deadline=datetime.now(timezone.utc) + timedelta(days=45),
    )


_EXTRACT_JSON = (
    '[{"id":"REQ-001","title":"Account lookup REST API","category":"functional",'
    '"priority":"MUST","summary":"Expose REST API."}]'
)
_SYNTH_JSON = (
    '{"executive_summary":"secure banking API","business_objectives":["digital"],'
    '"scope":{"in_scope":["API"],"out_of_scope":[]},'
    '"functional_requirements":[{"id":"REQ-001","title":"t","description":"d","priority":"MUST","rationale":"r"}],'
    '"assumptions":[],"constraints":[],"success_criteria":[],"risks":[],'
    '"similar_projects":[],"confidence":0.82,"sources":[]}'
)
_CRITIQUE_JSON = '{"coverage_gaps":[],"quality_issues":[],"confidence":0.82}'


def _fake_final(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=SONNET,
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


class _FakeStream:
    def __init__(self, deltas: list[str], final: SimpleNamespace) -> None:
        self._deltas = deltas
        self._final = final

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            for delta in self._deltas:
                yield delta

        return _gen()

    async def get_final_message(self) -> SimpleNamespace:
        return self._final


def _kb_hits() -> list[dict[str, Any]]:
    return [
        {
            "content": "banking ref",
            "score": 0.7,
            "source_path": "kb/x.md",
            "metadata": {"domain": "banking"},
        }
    ]


class _CaptureRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def aclose(self) -> None:
        pass


async def test_ba_agent_publishes_tokens_when_publisher_bound() -> None:
    """BA agent must route through generate_stream when a publisher is bound + push tokens per node."""
    # Streams: extract (Haiku), synth (Sonnet), critique (Sonnet).
    streams = [
        _FakeStream(list(_EXTRACT_JSON), _fake_final(_EXTRACT_JSON)),
        _FakeStream(list(_SYNTH_JSON), _fake_final(_SYNTH_JSON)),
        _FakeStream(list(_CRITIQUE_JSON), _fake_final(_CRITIQUE_JSON)),
    ]
    stream_iter = iter(streams)

    def _stream_factory(**_kwargs: Any) -> _FakeStream:
        return next(stream_iter)

    kb_mock = AsyncMock(return_value=_kb_hits())

    capture = _CaptureRedis()
    pub = TokenPublisher(
        bid_id="b1", agent="ba", attempt=1, client=capture, threshold_chars=10
    )

    with (
        patch("agents.ba_agent.kb_search_mod.kb_search", kb_mock),
        patch(
            "tools.claude_client.ClaudeClient._get_client",
            lambda self: SimpleNamespace(
                messages=SimpleNamespace(
                    create=AsyncMock(), stream=_stream_factory
                )
            ),
        ),
    ):
        async with stream_context(pub):
            draft = await ba_agent.run_ba_agent(_sample_input())

    # Final draft still parseable from streamed JSON.
    assert draft.executive_summary == "secure banking API"
    assert draft.confidence == 0.82

    # Expect at least one publish per node + one done per node.
    import json

    decoded = [json.loads(msg) for _, msg in capture.published]
    nodes_seen = {e["node"] for e in decoded}
    assert {"extract_requirements", "synthesize_draft", "self_critique"} <= nodes_seen
    # Each node must emit at least one done=True terminator.
    done_by_node = {e["node"] for e in decoded if e["done"]}
    assert done_by_node >= {"extract_requirements", "synthesize_draft", "self_critique"}
    # attempt number propagates.
    assert all(e["attempt"] == 1 for e in decoded)
    await pub.aclose()


# ---------------------------------------------------------------------------
# SA + Domain symmetric coverage — same pattern, different prompts/node names.
# Catches `node_name` typos or publisher-lifecycle drift if wrappers evolve.
# ---------------------------------------------------------------------------

_SA_CLASSIFY_JSON = '[{"id":"REQ-001","signals":["api"],"notes":"REST"}]'
_SA_SYNTH_JSON = (
    '{"tech_stack":[{"layer":"API","choice":"NestJS","rationale":"ok"}],'
    '"architecture_patterns":[],"nfr_targets":{"availability":"99.9%"},'
    '"technical_risks":[],"integrations":[],"confidence":0.82,"sources":[]}'
)
_SA_CRITIQUE_JSON = '{"coverage_gaps":[],"quality_issues":[],"confidence":0.82}'

_DM_TAG_JSON = '[{"id":"REQ-001","domain_tags":["banking"],"notes":"core"}]'
_DM_SYNTH_JSON = (
    '{"compliance":[{"framework":"PCI DSS","requirement":"encrypt","applies":true}],'
    '"best_practices":[],"industry_constraints":[],"glossary":{},"confidence":0.80,"sources":[]}'
)
_DM_CRITIQUE_JSON = '{"coverage_gaps":[],"quality_issues":[],"confidence":0.80}'


async def test_sa_agent_publishes_tokens_per_node_when_publisher_bound() -> None:
    """SA agent must route all 3 LLM nodes through generate_stream with the right node names."""
    streams = [
        _FakeStream(list(_SA_CLASSIFY_JSON), _fake_final(_SA_CLASSIFY_JSON)),
        _FakeStream(list(_SA_SYNTH_JSON), _fake_final(_SA_SYNTH_JSON)),
        _FakeStream(list(_SA_CRITIQUE_JSON), _fake_final(_SA_CRITIQUE_JSON)),
    ]
    stream_iter = iter(streams)
    kb_mock = AsyncMock(return_value=_kb_hits())
    capture = _CaptureRedis()
    pub = TokenPublisher(
        bid_id="b1", agent="sa", attempt=1, client=capture, threshold_chars=10
    )

    with (
        patch("agents.sa_agent.kb_search_mod.kb_search", kb_mock),
        patch(
            "tools.claude_client.ClaudeClient._get_client",
            lambda self: SimpleNamespace(
                messages=SimpleNamespace(
                    create=AsyncMock(), stream=lambda **_kw: next(stream_iter)
                )
            ),
        ),
    ):
        async with stream_context(pub):
            draft = await sa_agent.run_sa_agent(_sample_input())

    assert draft.tech_stack and draft.tech_stack[0].layer == "API"

    import json

    decoded = [json.loads(msg) for _, msg in capture.published]
    nodes_seen = {e["node"] for e in decoded}
    assert {"classify_signals", "synthesize_draft", "self_critique"} <= nodes_seen
    done_by_node = {e["node"] for e in decoded if e["done"]}
    assert done_by_node >= {"classify_signals", "synthesize_draft", "self_critique"}
    assert all(e["agent"] == "sa" and e["attempt"] == 1 for e in decoded)
    await pub.aclose()


async def test_domain_agent_publishes_tokens_per_node_when_publisher_bound() -> None:
    """Domain agent must route all 3 LLM nodes through generate_stream with the right node names."""
    streams = [
        _FakeStream(list(_DM_TAG_JSON), _fake_final(_DM_TAG_JSON)),
        _FakeStream(list(_DM_SYNTH_JSON), _fake_final(_DM_SYNTH_JSON)),
        _FakeStream(list(_DM_CRITIQUE_JSON), _fake_final(_DM_CRITIQUE_JSON)),
    ]
    stream_iter = iter(streams)
    kb_mock = AsyncMock(return_value=_kb_hits())
    capture = _CaptureRedis()
    pub = TokenPublisher(
        bid_id="b1", agent="domain", attempt=1, client=capture, threshold_chars=10
    )

    with (
        patch("agents.domain_agent.kb_search_mod.kb_search", kb_mock),
        patch(
            "tools.claude_client.ClaudeClient._get_client",
            lambda self: SimpleNamespace(
                messages=SimpleNamespace(
                    create=AsyncMock(), stream=lambda **_kw: next(stream_iter)
                )
            ),
        ),
    ):
        async with stream_context(pub):
            notes = await domain_agent.run_domain_agent(_sample_input())

    assert notes.compliance and notes.compliance[0].framework == "PCI DSS"

    import json

    decoded = [json.loads(msg) for _, msg in capture.published]
    nodes_seen = {e["node"] for e in decoded}
    assert {"tag_atoms", "synthesize_draft", "self_critique"} <= nodes_seen
    done_by_node = {e["node"] for e in decoded if e["done"]}
    assert done_by_node >= {"tag_atoms", "synthesize_draft", "self_critique"}
    assert all(e["agent"] == "domain" and e["attempt"] == 1 for e in decoded)
    await pub.aclose()


async def test_ba_agent_falls_through_to_generate_when_no_publisher() -> None:
    """Without stream_context the agent must still work via the legacy generate path."""
    kb_mock = AsyncMock(return_value=_kb_hits())
    generate_mock = AsyncMock(
        side_effect=[
            ClaudeResponse(text=_EXTRACT_JSON, model=HAIKU),
            ClaudeResponse(text=_SYNTH_JSON, model=SONNET),
            ClaudeResponse(text=_CRITIQUE_JSON, model=SONNET),
        ]
    )

    with (
        patch("agents.ba_agent.kb_search_mod.kb_search", kb_mock),
        patch("tools.claude_client.ClaudeClient.generate", generate_mock),
    ):
        draft = await ba_agent.run_ba_agent(_sample_input())

    assert draft.executive_summary == "secure banking API"
    assert generate_mock.await_count == 3
