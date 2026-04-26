"""S0.5 Wave 2A — synth unit tests.

Stub path covered by the autouse no-key fixture; LLM path uses scripted
Fake client + monkeypatch'd ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from parsers.models import BidCardSuggestion
from parsers.synth import (
    SynthOutput,
    _atom_summary,
    _stub_anchor,
    _stub_open_questions,
    _stub_summary,
    synthesize_context,
)
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


def _atom(idx: int = 1, *, atom_type: str = "functional", confidence: float = 0.6) -> AtomFrontmatter:
    type_prefix = {
        "functional": "F",
        "nfr": "NFR",
        "compliance": "C",
        "unclear": "U",
    }[atom_type]
    return AtomFrontmatter(
        id=f"REQ-{type_prefix}-{idx:03d}",
        type=atom_type,  # type: ignore[arg-type]
        priority="MUST",
        category="general",
        source=AtomSource(file="sources/01.md"),
        extraction=AtomExtraction(
            parser="heuristic_v1",
            confidence=confidence,
            extracted_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        ),
        verification=AtomVerification(),
        links=AtomLinks(),
        tenant_id="acme",
        bid_id="session-1",
    )


def _file() -> ParsedFile:
    return ParsedFile(file_id="01", name="rfp.pdf", role="rfp", raw_text="text")


def test_atom_summary_counts_by_type_and_priority() -> None:
    pairs = [
        (_atom(1, atom_type="functional"), "body1"),
        (_atom(2, atom_type="nfr"), "body2"),
        (_atom(3, atom_type="functional"), "body3"),
    ]
    summary = _atom_summary(pairs)
    assert summary["total"] == 3
    assert summary["by_type"]["functional"] == 2
    assert summary["by_type"]["nfr"] == 1


def test_stub_anchor_includes_client_and_atoms() -> None:
    bc = BidCardSuggestion(client_name="Acme Bank", industry="banking")
    anchor = _stub_anchor(bc, {"total": 5, "by_priority": {"MUST": 3}, "by_type": {"functional": 4}})
    assert "Acme Bank" in anchor
    assert "banking" in anchor
    assert "Total atoms: 5" in anchor


def test_stub_summary_lists_files_and_atom_mix() -> None:
    bc = BidCardSuggestion(client_name="Acme")
    summary = _stub_summary(bc, [_file()], {"total": 2, "by_type": {"functional": 1, "compliance": 1}})
    assert "Acme" in summary
    assert "rfp.pdf" in summary
    assert "Compliance: 1" in summary


def test_stub_open_questions_aggregates_unclear_atoms() -> None:
    pairs = [
        (_atom(1, atom_type="unclear"), "Vague body that needs review"),
        (_atom(2, confidence=0.4), "Low confidence atom"),
    ]
    questions = _stub_open_questions(pairs, [_file()])
    assert len(questions) >= 2
    assert any("REQ-U-001" in q for q in questions)


@pytest.mark.asyncio
async def test_synthesize_context_stub_path_returns_template_output() -> None:
    bc = BidCardSuggestion(client_name="Acme", industry="banking")
    out = await synthesize_context([_file()], [(_atom(), "body")], bc)
    assert isinstance(out, SynthOutput)
    assert "Acme" in out.anchor_md
    assert "Acme" in out.summary_md


@pytest.mark.asyncio
async def test_synthesize_context_llm_path_parses_response(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from config.llm import get_llm_settings

    get_llm_settings.cache_clear()

    synth_payload = json.dumps({
        "anchor_md": "# Anchor\nSome anchor body.",
        "summary_md": "# Summary\nSome summary body.",
        "open_questions": ["What is the budget cap?"],
    })
    critique_payload = json.dumps({
        "gaps": [],
        "factual_concerns": [],
        "additional_questions": ["Confirm timeline."],
        "overall_confidence": 0.85,
    })
    fake = FakeLLMClient(
        [
            ScriptedResponse(text=synth_payload, usage=TokenUsage(input_tokens=200, output_tokens=120)),
            ScriptedResponse(text=critique_payload, usage=TokenUsage(input_tokens=120, output_tokens=40)),
        ]
    )
    set_default_client(fake)
    try:
        bc = BidCardSuggestion(client_name="Acme")
        out = await synthesize_context([_file()], [(_atom(), "body")], bc)
        assert "Anchor" in out.anchor_md
        assert "Summary" in out.summary_md
        # Critique additional question merged into open_questions.
        assert "Confirm timeline." in out.open_questions
        assert "What is the budget cap?" in out.open_questions
    finally:
        set_default_client(None)


@pytest.mark.asyncio
async def test_synthesize_context_falls_back_to_stub_on_garbage_json(monkeypatch) -> None:
    """When the LLM returns un-parseable text, wrapper should silently degrade."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from config.llm import get_llm_settings

    get_llm_settings.cache_clear()

    fake = FakeLLMClient(ScriptedResponse(text="not json at all", usage=TokenUsage()))
    set_default_client(fake)
    try:
        bc = BidCardSuggestion(client_name="Acme")
        out = await synthesize_context([_file()], [(_atom(), "body")], bc)
        # Stub path engaged → anchor mentions the atom mix template.
        assert "Acme" in out.anchor_md
        assert "Total atoms" in out.anchor_md
    finally:
        set_default_client(None)
