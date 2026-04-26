"""S0.5 Wave 2A — atom_extractor unit tests.

Default tests run on the heuristic path (autouse fixture scrubs LLM keys);
LLM-path specs use ``monkeypatch`` to flip the gate + inject a scripted Fake.
"""

from __future__ import annotations

import json

import pytest

from parsers.atom_extractor import (
    _AtomCandidate,
    _assign_atom_ids,
    _heuristic_extract,
    _heuristic_priority,
    _heuristic_type,
    _split_chunks,
    extract_atoms,
)
from tools.llm.client import set_default_client
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.base import ParsedFile


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def _file(text: str, *, name: str = "rfp.pdf", lang: str = "en") -> ParsedFile:
    return ParsedFile(file_id="01-rfp", name=name, raw_text=text, language=lang)


def test_heuristic_priority_picks_must_for_shall() -> None:
    assert _heuristic_priority("The system shall do X") == "MUST"
    assert _heuristic_priority("Required to integrate with AD") == "MUST"


def test_heuristic_priority_picks_should_for_should_token() -> None:
    assert _heuristic_priority("The system should do X") == "SHOULD"


def test_heuristic_priority_picks_could_for_may() -> None:
    assert _heuristic_priority("The system may do X") == "COULD"


def test_heuristic_type_picks_compliance_for_hipaa() -> None:
    assert _heuristic_type("HIPAA compliance required") == "compliance"


def test_heuristic_type_picks_nfr_for_latency() -> None:
    assert _heuristic_type("p95 latency under 500ms") == "nfr"


def test_heuristic_extract_pulls_bullets() -> None:
    pf = _file("- Shall support SSO\n- HIPAA required\n- p95 latency 500ms\n")
    cands = _heuristic_extract(pf)
    assert len(cands) == 3
    assert cands[0].priority == "MUST"
    assert cands[1].type == "compliance"


def test_heuristic_extract_falls_back_to_modal_sentences() -> None:
    pf = _file("The system shall handle this. The system must do that.")
    cands = _heuristic_extract(pf)
    assert len(cands) >= 2


def test_assign_atom_ids_uses_type_prefix() -> None:
    cands = [
        _AtomCandidate(type="functional", priority="MUST", body="x"),
        _AtomCandidate(type="nfr", priority="MUST", body="y"),
        _AtomCandidate(type="functional", priority="SHOULD", body="z"),
    ]
    ids = _assign_atom_ids(cands)
    assert [pair[0] for pair in ids] == ["REQ-F-001", "REQ-NFR-001", "REQ-F-002"]


def test_split_chunks_returns_single_chunk_under_limit() -> None:
    text = "Hello world.\n\n" * 10
    chunks = _split_chunks(text, limit=10_000)
    assert len(chunks) == 1


def test_split_chunks_breaks_long_text_on_paragraph_boundary() -> None:
    text = ("para a.\n\n" * 1000).strip()
    chunks = _split_chunks(text, limit=200)
    assert len(chunks) > 1
    # Each chunk has trimmed content.
    for c in chunks:
        assert c.strip()


@pytest.mark.asyncio
async def test_extract_atoms_heuristic_path_marks_ai_generated_false() -> None:
    pf = _file("- The system shall do X\n- HIPAA compliance required")
    atoms = await extract_atoms(pf, bid_id="session-1", tenant_id="acme")
    assert len(atoms) == 2
    for front, _ in atoms:
        assert front.ai_generated is False
        assert front.extraction.parser == "heuristic_v1"
        assert front.extraction.confidence == 0.5
        assert front.tenant_id == "acme"
        assert front.bid_id == "session-1"


@pytest.mark.asyncio
async def test_extract_atoms_uses_llm_path_when_key_set(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from config.llm import get_llm_settings

    get_llm_settings.cache_clear()

    payload = json.dumps([
        {
            "id_seq": 1,
            "type": "functional",
            "priority": "MUST",
            "category": "user_management",
            "title": "Login support",
            "body": "Users shall sign in via SSO.",
            "section": "3.1",
            "page": 4,
            "line_range": [10, 15],
            "tags": ["auth"],
            "confidence": 0.9,
            "split_recommended": False,
        }
    ])
    fake = FakeLLMClient(ScriptedResponse(text=payload, usage=TokenUsage(input_tokens=200, output_tokens=80)))
    set_default_client(fake)
    try:
        pf = _file("# Auth\n\nUsers must sign in via SSO.")
        atoms = await extract_atoms(pf, bid_id="session-1", tenant_id="acme")
        assert len(atoms) == 1
        front, body = atoms[0]
        assert front.ai_generated is True
        assert front.extraction.parser == "rfp_extractor_v2.1"
        assert front.priority == "MUST"
        assert front.tags == ["auth"]
    finally:
        set_default_client(None)
