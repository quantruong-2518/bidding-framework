"""Conv 15 — S11 Retrospective real LLM via flagship tier; FakeLLMClient covers parse + invariants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agents.retrospective_agent import run_retrospective_agent
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import TokenUsage
from workflows.artifacts import (
    RetrospectiveInput,
    SubmissionRecord,
    WBSDraft,
    WBSItem,
)


def _submission() -> SubmissionRecord:
    return SubmissionRecord(
        bid_id=uuid4(),
        submitted_at=datetime.now(timezone.utc),
        confirmation_id="CONF-123",
        package_checksum="deadbeef",
        checklist={"consistency_checks_passed": True},
    )


def _input(*, with_wbs: bool = True) -> RetrospectiveInput:
    bid_id = uuid4()
    wbs = (
        WBSDraft(
            bid_id=bid_id,
            items=[WBSItem(id="WBS-300", name="Build", effort_md=80.0)],
            total_effort_md=80.0,
            timeline_weeks=4,
            critical_path=["WBS-300"],
        )
        if with_wbs
        else None
    )
    return RetrospectiveInput(
        bid_id=bid_id,
        submission=_submission(),
        wbs=wbs,
        client_name="Acme Bank",
        industry="banking",
    )


def _scripted_retro(outcome: str = "PENDING") -> ScriptedResponse:
    payload = {
        "outcome": outcome,
        "lessons": [
            {"title": "Effort vs estimate delta",
             "category": "estimation",
             "detail": "Build phase ran ~10% over MD; tune SA effort multiplier."},
            {"title": "Reviewer comment loop tight",
             "category": "process",
             "detail": "S9 closed in one round — preserve checklist discipline."},
        ],
        "kb_deltas": [
            {"id": "DELTA-001",
             "type": "new_lesson",
             "title": "Banking API margin tuning",
             "content_markdown": "# Banking margin\n\nUse 18% baseline.",
             "rationale": "captured from Acme bid retro"},
        ],
    }
    return ScriptedResponse(
        text=json.dumps(payload),
        usage=TokenUsage(input_tokens=600, output_tokens=240),
        cost_usd=0.0028,
        model="fake/flagship",
        provider="fake",
    )


@pytest.mark.asyncio
async def test_retrospective_agent_emits_lessons_and_kb_deltas() -> None:
    fake = FakeLLMClient(_scripted_retro())
    payload = _input()

    draft = await run_retrospective_agent(payload, client=fake)

    assert len(draft.lessons) == 2
    assert any(l.category == "estimation" for l in draft.lessons)
    assert len(draft.kb_deltas) == 1
    delta = draft.kb_deltas[0]
    assert delta.id == "DELTA-001"
    assert delta.ai_generated is True
    # Wrapper enforces the vault path even when LLM omits / lies about target_path.
    assert delta.target_path == f"lessons/{payload.bid_id}-DELTA-001.md"
    # Legacy mirror so older code reading kb_updates still gets a path list.
    assert draft.kb_updates == [delta.target_path]
    assert draft.llm_tier_used == "flagship"
    assert draft.llm_cost_usd == pytest.approx(0.0028, abs=1e-6)


@pytest.mark.asyncio
async def test_retrospective_agent_uses_flagship_tier_and_trace_id() -> None:
    fake = FakeLLMClient(_scripted_retro())
    payload = _input()

    await run_retrospective_agent(payload, client=fake)

    fake.assert_called(1)
    assert fake.calls[0].tier == "flagship"
    assert fake.calls[0].trace_id == str(payload.bid_id)
    assert fake.calls[0].node_name == "retrospective_agent.synthesise"


@pytest.mark.asyncio
async def test_retrospective_agent_rewrites_duplicate_delta_ids() -> None:
    """LLM may emit collision-prone ids — wrapper sequences them deterministically."""
    payload_two_dupes = json.dumps(
        {
            "outcome": "WIN",
            "lessons": [
                {"title": "x", "category": "process", "detail": "y"},
            ],
            "kb_deltas": [
                {"id": "DUP", "type": "new_lesson", "title": "a",
                 "content_markdown": "# a", "rationale": "r"},
                {"id": "DUP", "type": "new_lesson", "title": "b",
                 "content_markdown": "# b", "rationale": "r"},
            ],
        }
    )
    fake = FakeLLMClient(ScriptedResponse(text=payload_two_dupes))
    payload = _input(with_wbs=False)

    draft = await run_retrospective_agent(payload, client=fake)
    ids = [d.id for d in draft.kb_deltas]
    assert ids[0] == "DUP"
    assert ids[1] != "DUP"
    assert len(set(ids)) == 2


@pytest.mark.asyncio
async def test_retrospective_agent_coerces_unknown_outcome_to_pending() -> None:
    weird = ScriptedResponse(
        text=json.dumps(
            {
                "outcome": "won-someday",
                "lessons": [{"title": "x", "category": "process", "detail": "y"}],
                "kb_deltas": [],
            }
        )
    )
    fake = FakeLLMClient(weird)
    draft = await run_retrospective_agent(_input(with_wbs=False), client=fake)
    assert draft.outcome == "PENDING"


@pytest.mark.asyncio
async def test_retrospective_agent_raises_on_empty_lessons() -> None:
    bad = ScriptedResponse(
        text=json.dumps({"outcome": "PENDING", "lessons": [], "kb_deltas": []})
    )
    fake = FakeLLMClient(bad)
    with pytest.raises(ValueError, match="empty lessons"):
        await run_retrospective_agent(_input(), client=fake)


@pytest.mark.asyncio
async def test_retrospective_agent_raises_on_garbage_json() -> None:
    fake = FakeLLMClient(ScriptedResponse(text="not even close"))
    with pytest.raises(Exception):
        await run_retrospective_agent(_input(), client=fake)


@pytest.mark.asyncio
async def test_retrospective_agent_serialises_optional_phases_when_present() -> None:
    """Wrapper sends WBS context when the input has it; nothing when it doesn't."""
    fake_with = FakeLLMClient(_scripted_retro())
    await run_retrospective_agent(_input(with_wbs=True), client=fake_with)
    body_with = fake_with.calls[0].messages[-1].content
    assert '"wbs"' in body_with
    assert '"total_effort_md"' in body_with

    fake_without = FakeLLMClient(_scripted_retro())
    await run_retrospective_agent(_input(with_wbs=False), client=fake_without)
    body_without = fake_without.calls[0].messages[-1].content
    assert '"wbs"' not in body_without
