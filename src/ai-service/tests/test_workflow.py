"""End-to-end workflow tests using Temporal's time-skipping test environment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from activities.intake import intake_activity
from activities.scoping import scoping_activity
from activities.triage import triage_activity
from workflows.bid_workflow import BidWorkflow
from workflows.models import BidState, BidWorkflowInput, HumanTriageSignal, IntakeInput

TASK_QUEUE = "test-bid-queue"

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
            activities=[intake_activity, triage_activity, scoping_activity],
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
async def test_workflow_approve_reaches_s2_done() -> None:
    result = await _run_with_signal(
        HumanTriageSignal(approved=True, reviewer="alice", notes=None, bid_profile_override="M")
    )
    assert result.current_state == "S2_DONE"
    assert result.bid_card is not None
    assert result.triage is not None
    assert result.scoping is not None
    assert result.profile == "M"
    assert len(result.scoping.requirement_map) >= 1


@pytest.mark.asyncio
async def test_workflow_reject_terminates_at_s1_no_bid() -> None:
    result = await _run_with_signal(
        HumanTriageSignal(approved=False, reviewer="bob", notes="not strategic")
    )
    assert result.current_state == "S1_NO_BID"
    assert result.triage is not None
    assert result.scoping is None


@pytest.mark.asyncio
async def test_workflow_query_state_while_running() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter,
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BidWorkflow],
            activities=[intake_activity, triage_activity, scoping_activity],
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
            assert snapshot.current_state == final.current_state


@pytest.mark.asyncio
async def test_workflow_gate_timeout_results_in_no_bid() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter,
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BidWorkflow],
            activities=[intake_activity, triage_activity, scoping_activity],
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
