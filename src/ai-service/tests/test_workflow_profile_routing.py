"""Phase 2.6 — profile pipeline routing tests.

Bid-S runs a minimal pipeline (skips S5 Solution Design + S7 Commercial).
Bid-M / L / XL run the full 12-state pipeline. All terminate at S11_DONE.
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

from tests.test_workflow import _ALL_ACTIVITIES, _approve_review

TASK_QUEUE = "test-profile-queue"

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


async def _run_for_profile(profile: BidProfile):
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
                id=f"test-profile-{profile}-{uuid4()}",
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
            # Pre-queue enough approvals for each profile's reviewer count so
            # the review gate clears without waiting.
            for _ in range({"S": 1, "M": 1, "L": 3, "XL": 5}[profile]):
                await handle.signal("human_review_decision", _approve_review())
            return await handle.result()


@pytest.mark.asyncio
async def test_bid_s_skips_s5_and_s7() -> None:
    """Bid-S: HLD + pricing should be None; proposal package should still assemble."""
    result = await _run_for_profile("S")
    assert result.current_state == "S11_DONE"
    assert result.profile == "S"
    assert result.hld is None, "Bid-S must skip S5 (HLD)"
    assert result.pricing is None, "Bid-S must skip S7 (Pricing)"
    assert result.proposal_package is not None, "S8 assembly must still run"
    assert result.submission is not None, "S10 submission must run"
    assert result.retrospective is not None, "S11 retrospective must run"


@pytest.mark.asyncio
async def test_bid_m_runs_full_pipeline() -> None:
    result = await _run_for_profile("M")
    assert result.current_state == "S11_DONE"
    assert result.profile == "M"
    assert result.hld is not None
    assert result.pricing is not None
    assert result.proposal_package is not None


@pytest.mark.asyncio
async def test_bid_l_runs_full_pipeline() -> None:
    result = await _run_for_profile("L")
    assert result.current_state == "S11_DONE"
    assert result.profile == "L"
    assert result.hld is not None
    assert result.pricing is not None


@pytest.mark.asyncio
async def test_bid_xl_runs_l_pipeline_with_parity_pending_log() -> None:
    """XL falls back to L pipeline until Phase 3 adds S3d/S3e parity."""
    result = await _run_for_profile("XL")
    assert result.current_state == "S11_DONE"
    assert result.profile == "XL"
    assert result.hld is not None
    assert result.pricing is not None
