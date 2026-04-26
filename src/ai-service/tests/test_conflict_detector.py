"""S0.5 Wave 2A — conflict_detector unit tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from parsers.conflict_detector import ConflictItem, _heuristic_conflicts, detect_conflicts
from tools.llm.client import set_default_client
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.base import (
    AtomExtraction,
    AtomFrontmatter,
    AtomLinks,
    AtomSource,
    AtomVerification,
    ParsedFile,
)


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def _atom(
    idx: int,
    *,
    priority: str = "MUST",
    atom_type: str = "functional",
    file_path: str = "sources/01-rfp.md",
    category: str = "user_management",
) -> AtomFrontmatter:
    type_prefix = {
        "functional": "F",
        "compliance": "C",
        "nfr": "NFR",
        "technical": "T",
    }[atom_type]
    return AtomFrontmatter(
        id=f"REQ-{type_prefix}-{idx:03d}",
        type=atom_type,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        category=category,
        source=AtomSource(file=file_path),
        extraction=AtomExtraction(
            parser="heuristic_v1", confidence=0.7,
            extracted_at=datetime(2026, 4, 26, tzinfo=timezone.utc)
        ),
        verification=AtomVerification(),
        links=AtomLinks(),
        tenant_id="acme",
        bid_id="session-1",
    )


def test_heuristic_conflicts_detects_priority_disagreement() -> None:
    atoms = [
        _atom(1, priority="MUST", file_path="sources/01.md"),
        _atom(2, priority="WONT", file_path="sources/02.md"),
    ]
    conflicts = _heuristic_conflicts(atoms)
    topics = [c.topic for c in conflicts]
    assert any("priority_disagreement" in t for t in topics)


def test_heuristic_conflicts_detects_type_drift() -> None:
    atoms = [
        _atom(1, atom_type="functional", file_path="sources/01.md", category="audit"),
        _atom(2, atom_type="compliance", file_path="sources/02.md", category="audit"),
    ]
    conflicts = _heuristic_conflicts(atoms)
    topics = [c.topic for c in conflicts]
    assert any("type_drift_audit" in t for t in topics)


def test_heuristic_conflicts_returns_empty_when_no_disagreement() -> None:
    atoms = [
        _atom(1, priority="MUST"),
        _atom(2, priority="MUST"),
    ]
    assert _heuristic_conflicts(atoms) == []


@pytest.mark.asyncio
async def test_detect_conflicts_uses_heuristic_only_when_no_key() -> None:
    atoms = [
        _atom(1, priority="MUST", file_path="sources/01.md"),
        _atom(2, priority="WONT", file_path="sources/02.md"),
    ]
    files = [ParsedFile(file_id="01", name="01.pdf"), ParsedFile(file_id="02", name="02.pdf")]
    out = await detect_conflicts(atoms, files)
    assert len(out) == 1
    assert "priority_disagreement" in out[0].topic


@pytest.mark.asyncio
async def test_detect_conflicts_merges_llm_topics_when_key_set(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from config.llm import get_llm_settings

    get_llm_settings.cache_clear()

    llm_payload = json.dumps([
        {
            "topic": "deadline_mismatch",
            "severity": "HIGH",
            "description": "RFP says Q3 but appendix says Q2",
            "atoms": ["REQ-F-001", "REQ-F-002"],
            "files": ["01-rfp", "02-appendix"],
            "proposed_resolution": "confirm with bid manager",
        }
    ])
    fake = FakeLLMClient(ScriptedResponse(text=llm_payload, usage=TokenUsage()))
    set_default_client(fake)
    try:
        atoms = [
            _atom(1, priority="MUST", file_path="sources/01.md"),
            _atom(2, priority="WONT", file_path="sources/02.md"),
        ]
        files = [ParsedFile(file_id="01", name="01.pdf")]
        out = await detect_conflicts(atoms, files)
        topics = {c.topic for c in out}
        # Heuristic + LLM merged.
        assert any("priority_disagreement" in t for t in topics)
        assert "deadline_mismatch" in topics
    finally:
        set_default_client(None)
