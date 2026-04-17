"""End-to-end workflow tests using Temporal's time-skipping test environment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from activities.assembly import assembly_activity
from activities.commercial import commercial_activity
from activities.convergence import convergence_activity
from activities.intake import intake_activity
from activities.retrospective import retrospective_activity
from activities.review import review_activity
from activities.scoping import scoping_activity
from activities.solution_design import solution_design_activity
from activities.stream_stubs import (
    ba_analysis_stub_activity,
    domain_mining_stub_activity,
    sa_analysis_stub_activity,
)
from activities.submission import submission_activity
from activities.triage import triage_activity
from activities.wbs import wbs_activity
from workflows.bid_workflow import BidWorkflow
from workflows.models import BidState, BidWorkflowInput, HumanTriageSignal, IntakeInput

TASK_QUEUE = "test-bid-queue"

_ALL_ACTIVITIES = [
    intake_activity,
    triage_activity,
    scoping_activity,
    ba_analysis_stub_activity,
    sa_analysis_stub_activity,
    domain_mining_stub_activity,
    convergence_activity,
    solution_design_activity,
    wbs_activity,
    commercial_activity,
    assembly_activity,
    review_activity,
    submission_activity,
    retrospective_activity,
]

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


async def _run_with_signal(signal: HumanTriageSignal):
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
                id=f"test-{uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("human_triage_decision", signal)
            return await handle.result()


@pytest.mark.asyncio
async def test_workflow_approve_runs_full_pipeline_to_s11_done() -> None:
    result = await _run_with_signal(
        HumanTriageSignal(approved=True, reviewer="alice", notes=None, bid_profile_override="M")
    )
    assert result.current_state == "S11_DONE"
    assert result.bid_card is not None
    assert result.triage is not None
    assert result.scoping is not None
    assert result.profile == "M"
    assert len(result.scoping.requirement_map) >= 1


@pytest.mark.asyncio
async def test_workflow_full_pipeline_populates_all_artifacts() -> None:
    result = await _run_with_signal(
        HumanTriageSignal(approved=True, reviewer="alice", bid_profile_override="M")
    )
    # Each S3..S11 step should have produced its artifact.
    assert result.ba_draft is not None, "S3a BA draft missing"
    assert result.sa_draft is not None, "S3b SA draft missing"
    assert result.domain_notes is not None, "S3c domain notes missing"
    assert result.convergence is not None, "S4 convergence missing"
    assert result.hld is not None, "S5 HLD missing"
    assert result.wbs is not None, "S6 WBS missing"
    assert result.pricing is not None, "S7 pricing missing"
    assert result.proposal_package is not None, "S8 proposal package missing"
    assert len(result.reviews) >= 1, "S9 review record missing"
    assert result.submission is not None, "S10 submission missing"
    assert result.retrospective is not None, "S11 retrospective missing"

    # Sanity cross-checks on derived quantities.
    assert result.wbs.total_effort_md > 0
    assert result.pricing.total > 0
    assert len(result.proposal_package.sections) >= 5
    assert result.submission.confirmation_id is not None


@pytest.mark.asyncio
async def test_workflow_reject_terminates_at_s1_no_bid() -> None:
    result = await _run_with_signal(
        HumanTriageSignal(approved=False, reviewer="bob", notes="not strategic")
    )
    assert result.current_state == "S1_NO_BID"
    assert result.triage is not None
    assert result.scoping is None
    # None of the Phase 2.1 artifact fields should have fired.
    assert result.ba_draft is None
    assert result.proposal_package is None
    assert result.reviews == []


@pytest.mark.asyncio
async def test_workflow_query_state_while_running() -> None:
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
                id=f"test-query-{uuid4()}",
                task_queue=TASK_QUEUE,
            )
            # Approve so the workflow completes before we close the env.
            await handle.signal(
                "human_triage_decision", HumanTriageSignal(approved=True, reviewer="alice")
            )
            final = await handle.result()
            snapshot = await handle.query("get_state", result_type=BidState)
            assert snapshot.current_state == final.current_state == "S11_DONE"


@pytest.mark.asyncio
async def test_workflow_gate_timeout_results_in_no_bid() -> None:
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
                id=f"test-timeout-{uuid4()}",
                task_queue=TASK_QUEUE,
            )
            # Do not signal — the 24h gate should elapse under time-skipping.
            try:
                result = await handle.result()
            except WorkflowFailureError as exc:  # pragma: no cover — surfaces upstream
                raise AssertionError(f"workflow should not fail: {exc}") from exc
            assert result.current_state == "S1_NO_BID"
