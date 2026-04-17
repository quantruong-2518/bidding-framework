"""Phase 2.4 — S9 human review gate scenarios.

Covers: happy-path approve, CHANGES_REQUESTED with explicit target, earliest
target aggregation, max-rounds cap, REJECT terminal, Bid-S fall-forward,
timeout terminal, sequential multi-reviewer short-circuit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.base import BidProfile
from workflows.bid_workflow import BidWorkflow
from workflows.models import (
    BidWorkflowInput,
    HumanReviewSignal,
    HumanTriageSignal,
    IntakeInput,
)
from workflows.artifacts import ReviewComment

from tests.test_workflow import _ALL_ACTIVITIES, _approve_review

TASK_QUEUE = "test-review-gate-queue"

_RFP_TEXT = (
    "Modernise core banking platform.\n"
    "- The system shall expose REST APIs\n"
    "- Must run on Kubernetes and AWS\n"
    "- Users should be able to view transactions in React\n"
    "- Compliance: PCI DSS applies\n"
)


def _intake() -> IntakeInput:
    return IntakeInput(
        client_name="Acme Bank",
        rfp_text=_RFP_TEXT,
        deadline=datetime.now(timezone.utc) + timedelta(days=60),
        region="APAC",
        industry="banking",
    )


def _changes(target: str = "S5", section: str = "HLD") -> HumanReviewSignal:
    return HumanReviewSignal(
        verdict="CHANGES_REQUESTED",
        reviewer="qc",
        reviewer_role="qc",
        comments=[
            ReviewComment(
                section=section,
                severity="MAJOR",
                message=f"Rework {section}",
                target_state=target,  # type: ignore[arg-type]
            )
        ],
    )


def _reject() -> HumanReviewSignal:
    return HumanReviewSignal(
        verdict="REJECTED",
        reviewer="qc",
        reviewer_role="qc",
        comments=[],
        notes="not viable",
    )


async def _run(profile: BidProfile, review_signals: list[HumanReviewSignal]):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter,
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BidWorkflow],
            activities=_ALL_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                BidWorkflow.run,
                BidWorkflowInput(intake=_intake()),
                id=f"test-review-{uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal(
                "human_triage_decision",
                HumanTriageSignal(
                    approved=True,
                    reviewer="alice",
                    bid_profile_override=profile,
                ),
            )
            for sig in review_signals:
                await handle.signal("human_review_decision", sig)
            return await handle.result()


@pytest.mark.asyncio
async def test_round_1_approved_reaches_s11_done() -> None:
    result = await _run("M", [_approve_review("alice")])
    assert result.current_state == "S11_DONE"
    # pre-human record + human approve record for round 1.
    verdicts = [r.verdict for r in result.reviews]
    assert "APPROVED" in verdicts
    assert result.loop_back_history == []


@pytest.mark.asyncio
async def test_changes_requested_s5_loops_back_then_approves() -> None:
    result = await _run("M", [_changes("S5"), _approve_review("alice")])
    assert result.current_state == "S11_DONE"
    assert len(result.loop_back_history) == 1
    assert result.loop_back_history[0].target_state == "S5"
    # hld should have been re-produced after loop-back.
    assert result.hld is not None


@pytest.mark.asyncio
async def test_earliest_target_aggregation_picks_s2_over_s5() -> None:
    """Two comments pick S2 and S5 — earliest-first aggregation chooses S2."""
    mixed = HumanReviewSignal(
        verdict="CHANGES_REQUESTED",
        reviewer="qc",
        reviewer_role="qc",
        comments=[
            ReviewComment(section="HLD", severity="MAJOR", message="x", target_state="S5"),
            ReviewComment(section="Scope", severity="MAJOR", message="y", target_state="S2"),
        ],
    )
    result = await _run("M", [mixed, _approve_review("alice")])
    assert result.current_state == "S11_DONE"
    assert result.loop_back_history[0].target_state == "S2"


@pytest.mark.asyncio
async def test_three_changes_requested_hits_s9_blocked() -> None:
    result = await _run(
        "M",
        [_changes("S8"), _changes("S8"), _changes("S8")],
    )
    assert result.current_state == "S9_BLOCKED"
    assert len(result.loop_back_history) <= 3


@pytest.mark.asyncio
async def test_reject_on_round_1_is_terminal() -> None:
    result = await _run("M", [_reject()])
    assert result.current_state == "S9_BLOCKED"
    assert result.loop_back_history == []


@pytest.mark.asyncio
async def test_bid_s_falls_forward_when_target_skipped() -> None:
    """Bid-S pipeline has no S5 — target=S5 should fall forward to S6."""
    result = await _run("S", [_changes("S5"), _approve_review("alice")])
    assert result.current_state == "S11_DONE"
    assert len(result.loop_back_history) == 1
    # S5 is skipped for Bid-S; fall-forward lands on S6 (next loop-target in pipeline).
    assert result.loop_back_history[0].target_state == "S6"


@pytest.mark.asyncio
async def test_s9_timeout_without_signal_is_blocked() -> None:
    """No review signal → wait_condition fires timeout → S9_BLOCKED."""
    result = await _run("M", [])
    assert result.current_state == "S9_BLOCKED"


@pytest.mark.asyncio
async def test_bid_l_multi_reviewer_short_circuits_on_second_reject() -> None:
    """Bid-L requires 3 sequential approvals. Second reviewer changes → short-circuit."""
    result = await _run(
        "L",
        [
            _approve_review("reviewer-A"),
            _changes("S8", section="Commercial"),
            # Round 2 — three approvals.
            _approve_review("reviewer-A"),
            _approve_review("reviewer-B"),
            _approve_review("reviewer-C"),
        ],
    )
    assert result.current_state == "S11_DONE"
    assert len(result.loop_back_history) == 1
    assert result.loop_back_history[0].target_state == "S8"
