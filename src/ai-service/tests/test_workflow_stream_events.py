"""Phase 2.5 — workflow emits state_completed events per pipeline phase.

Uses the autouse `_stub_redis_publish` fixture in conftest to intercept the
Redis publish calls issued by `state_transition_activity`. Assertions compare
the emitted event stream against the declarative `_PROFILE_PIPELINE` matrix so
Bid-S is verified to skip S5/S7, and Bid-M receives the full sequence.
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
    HumanTriageSignal,
    IntakeInput,
)

from tests.test_workflow import _ALL_ACTIVITIES, _approve_review

TASK_QUEUE = "test-stream-events-queue"


def _intake() -> IntakeInput:
    return IntakeInput(
        client_name="Acme Bank",
        rfp_text=(
            "Modernise core banking platform.\n"
            "- The system shall expose REST APIs\n"
            "- Must run on Kubernetes and AWS\n"
            "- Compliance: PCI DSS applies\n"
        ),
        deadline=datetime.now(timezone.utc) + timedelta(days=60),
        region="APAC",
        industry="banking",
    )


async def _run(profile: BidProfile):
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
                id=f"test-stream-{profile}-{uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal(
                "human_triage_decision",
                HumanTriageSignal(approved=True, reviewer="alice", bid_profile_override=profile),
            )
            for _ in range({"S": 1, "M": 1, "L": 3, "XL": 5}[profile]):
                await handle.signal("human_review_decision", _approve_review())
            return await handle.result()


@pytest.mark.asyncio
async def test_bid_m_emits_full_state_completed_sequence(_stub_redis_publish) -> None:
    """Bid-M must fire state_completed for every phase from S0_DONE through S11_DONE."""
    await _run("M")
    phases = [e["state"] for e in _stub_redis_publish.events_of_type("state_completed")]
    expected = [
        "S0_DONE",
        "S1_DONE",
        "S2_DONE",
        "S3_DONE",
        "S4_DONE",
        "S5_DONE",
        "S6_DONE",
        "S7_DONE",
        "S8_DONE",
        "S9_DONE",
        "S10_DONE",
        "S11_DONE",
    ]
    assert phases == expected, f"Bid-M phases mismatch: {phases}"
    # Every event must carry the profile + non-null occurred_at + the expected artifact keys.
    by_phase = {e["state"]: e for e in _stub_redis_publish.events_of_type("state_completed")}
    assert by_phase["S3_DONE"]["artifact_keys"] == ["ba_draft", "sa_draft", "domain_notes"]
    assert by_phase["S4_DONE"]["artifact_keys"] == ["convergence"]
    assert by_phase["S5_DONE"]["artifact_keys"] == ["hld"]
    assert by_phase["S7_DONE"]["artifact_keys"] == ["pricing"]
    # S0/S1 fire BEFORE the triage override resolves, so they carry the
    # intake-estimated profile. S2 onwards carry the overridden profile.
    post_gate = [e for e in _stub_redis_publish.events_of_type("state_completed") if e["state"] not in ("S0_DONE", "S1_DONE")]
    assert all(e["profile"] == "M" for e in post_gate), [e["profile"] for e in post_gate]
    assert all("occurred_at" in e for e in by_phase.values())


@pytest.mark.asyncio
async def test_bid_s_skips_s5_and_s7_state_completed_events(_stub_redis_publish) -> None:
    """Bid-S must NOT emit S5_DONE / S7_DONE because those phases are skipped."""
    await _run("S")
    phases = [e["state"] for e in _stub_redis_publish.events_of_type("state_completed")]
    expected = [
        "S0_DONE",
        "S1_DONE",
        "S2_DONE",
        "S3_DONE",
        "S4_DONE",
        "S6_DONE",
        "S8_DONE",
        "S9_DONE",
        "S10_DONE",
        "S11_DONE",
    ]
    assert phases == expected, f"Bid-S phases mismatch: {phases}"
    assert "S5_DONE" not in phases
    assert "S7_DONE" not in phases
    # Profile propagates correctly (RFP is short → estimated "S" from intake
    # already matches the override, so every event carries "S").
    assert {e["profile"] for e in _stub_redis_publish.events_of_type("state_completed")} == {"S"}
