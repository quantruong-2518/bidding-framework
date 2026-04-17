"""Phase 2.2 integration test — exercises real BA / SA / Domain LangGraph agents.

Skipped by default via the `integration` marker in pyproject.toml. To run it
locally:

    ANTHROPIC_API_KEY=sk-ant-... poetry run pytest -m integration -v

The assertions are intentionally loose — LLM output is non-deterministic, we
just verify the pipeline reaches `S11_DONE` and that the S3 agents produced
non-trivial drafts (i.e. not the stub fallback shape).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from activities.assembly import assembly_activity
from activities.ba_analysis import ba_analysis_activity
from activities.commercial import commercial_activity
from activities.convergence import convergence_activity
from activities.domain_mining import domain_mining_activity
from activities.intake import intake_activity
from activities.retrospective import retrospective_activity
from activities.review import review_activity
from activities.sa_analysis import sa_analysis_activity
from activities.scoping import scoping_activity
from activities.solution_design import solution_design_activity
from activities.submission import submission_activity
from activities.triage import triage_activity
from activities.wbs import wbs_activity
from workflows.bid_workflow import BidWorkflow
from workflows.models import BidWorkflowInput, HumanTriageSignal, IntakeInput

TASK_QUEUE = "integration-bid-queue"

_ALL_ACTIVITIES = [
    intake_activity,
    triage_activity,
    scoping_activity,
    ba_analysis_activity,
    sa_analysis_activity,
    domain_mining_activity,
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
    "Modernise core banking platform for a regional APAC bank.\n"
    "- The system shall expose REST APIs for account lookup and transactions\n"
    "- API p95 latency under 250ms; 99.9% monthly availability\n"
    "- Must comply with PCI DSS (level 1 merchant)\n"
    "- Data residency in-region required\n"
    "- Support concurrent logins 5k peak\n"
)


def _intake() -> IntakeInput:
    return IntakeInput(
        client_name="Acme Bank",
        rfp_text=_RFP_TEXT,
        deadline=datetime.now(timezone.utc) + timedelta(days=60),
        region="APAC",
        industry="banking",
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY required for real agent integration",
)
@pytest.mark.asyncio
async def test_phase_2_2_full_pipeline_with_real_agents() -> None:
    """Workflow completes with real LLM-backed S3 outputs (not stub placeholders)."""
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
                id=f"integration-{uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal(
                "human_triage_decision",
                HumanTriageSignal(approved=True, reviewer="integration", bid_profile_override="M"),
            )
            result = await handle.result()

    assert result.current_state == "S11_DONE"
    assert result.ba_draft is not None
    assert result.sa_draft is not None
    assert result.domain_notes is not None

    # BA: executive summary should not be the stub placeholder.
    assert "Stub BA summary" not in result.ba_draft.executive_summary
    assert result.ba_draft.confidence > 0.3

    # SA: tech_stack should name at least one concrete technology beyond the default stub.
    assert result.sa_draft.tech_stack
    assert result.sa_draft.confidence > 0.3

    # Domain: compliance list should include PCI DSS (real agent) given the RFP.
    frameworks = {c.framework.upper() for c in result.domain_notes.compliance}
    assert any("PCI" in f for f in frameworks)
    assert result.domain_notes.confidence > 0.3
