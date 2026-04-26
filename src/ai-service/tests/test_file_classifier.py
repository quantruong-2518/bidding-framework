"""S0.5 Wave 2A — file_classifier unit tests.

The autouse ``_force_llm_fallback_by_default`` fixture in :mod:`tests.conftest`
scrubs every provider key + injects a :class:`FakeLLMClient`, so by default
this module exercises the heuristic path. Two specs flip the gate via
``monkeypatch`` to exercise the LLM path with a scripted Fake response.
"""

from __future__ import annotations

import pytest

from parsers.file_classifier import _heuristic_role, classify_file_role
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


def _make_file(name: str, body: str = "") -> ParsedFile:
    return ParsedFile(file_id="f", name=name, raw_text=body)


def test_heuristic_role_returns_rfp_for_rfp_in_filename() -> None:
    assert _heuristic_role("Banking_Core_RFP_v1.pdf") == "rfp"
    assert _heuristic_role("rfp.docx") == "rfp"


def test_heuristic_role_returns_qa_for_qa_keyword() -> None:
    assert _heuristic_role("Q&A_Round1.pdf") == "qa"
    assert _heuristic_role("addendum-clarification.pdf") == "qa"


def test_heuristic_role_returns_appendix_for_annex() -> None:
    assert _heuristic_role("Annex_A_Forms.docx") == "appendix"
    assert _heuristic_role("Schedule_5.docx") == "appendix"


def test_heuristic_role_returns_previous_for_prior_engagement() -> None:
    assert _heuristic_role("Acme_2024_previous_proposal.pdf") == "previous_engagement"


def test_heuristic_role_falls_back_to_reference_for_unknown() -> None:
    assert _heuristic_role("Random_Doc.pdf") == "reference"
    assert _heuristic_role("") == "reference"


@pytest.mark.asyncio
async def test_classify_file_role_uses_heuristic_when_no_key() -> None:
    """No provider key → heuristic path; LLM never invoked."""
    pf = _make_file("Banking_Core_RFP_v1.pdf", "shall provide loan onboarding")
    role = await classify_file_role(pf)
    assert role == "rfp"


@pytest.mark.asyncio
async def test_classify_file_role_uses_llm_when_key_set(monkeypatch) -> None:
    """When a key is set, the LLM result wins (Fake returns 'appendix')."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from config.llm import get_llm_settings

    get_llm_settings.cache_clear()

    fake = FakeLLMClient(
        ScriptedResponse(text="appendix", usage=TokenUsage(input_tokens=20, output_tokens=2))
    )
    set_default_client(fake)
    try:
        pf = _make_file("Banking_Core_RFP_v1.pdf", "supplementary forms")
        role = await classify_file_role(pf)
        assert role == "appendix"
        assert len(fake.calls) == 1
    finally:
        set_default_client(None)
