"""Temporal workflow — full 11-state DAG.

Order: S0 Intake -> S1 Triage (+ human gate) -> S2 Scoping ->
       S3 parallel (S3a BA / S3b SA / S3c Domain) -> S4 Convergence ->
       S5 Solution Design -> S6 WBS -> S7 Commercial -> S8 Assembly ->
       S9 Review -> S10 Submission -> S11 Retrospective -> S11_DONE.

Phase 2.2: S3a/b/c call the real LangGraph-backed activities
(`ba_analysis_activity`, `sa_analysis_activity`, `domain_mining_activity`).
Each activity falls back to its deterministic stub when ANTHROPIC_API_KEY is
not set, so the workflow stays runnable without an LLM key.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

_NIL_UUID = UUID(int=0)

with workflow.unsafe.imports_passed_through():
    from activities.assembly import assembly_activity
    from activities.ba_analysis import ba_analysis_activity
    from activities.bid_workspace import workspace_snapshot_activity
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
    from kb_writer.models import WorkspaceInput
    from workflows.artifacts import (
        AssemblyInput,
        BusinessRequirementsDraft,
        CommercialInput,
        ConvergenceInput,
        ConvergenceReport,
        DomainNotes,
        HLDDraft,
        PricingDraft,
        ProposalPackage,
        RetrospectiveDraft,
        RetrospectiveInput,
        ReviewInput,
        ReviewRecord,
        SolutionArchitectureDraft,
        SolutionDesignInput,
        StreamInput,
        SubmissionInput,
        SubmissionRecord,
        WBSDraft,
        WBSInput,
    )
    from workflows.models import (
        BidCard,
        BidState,
        BidWorkflowInput,
        HumanTriageSignal,
        ScopingResult,
        TriageDecision,
        WorkflowState,
    )

HUMAN_GATE_TIMEOUT = timedelta(hours=24)
ACTIVITY_TIMEOUT = timedelta(minutes=5)
# S3 streams may run 3 real LLM-backed LangGraph agents in parallel; give them
# more headroom than the default and emit heartbeats so Temporal doesn't fail
# the activity while Sonnet is thinking.
S3_ACTIVITY_TIMEOUT = timedelta(minutes=10)
S3_HEARTBEAT_TIMEOUT = timedelta(minutes=2)

_DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)

# Vault-snapshot writes are best-effort: bid completion must not block on
# filesystem issues. Short timeout + at most one retry.
_WORKSPACE_TIMEOUT = timedelta(seconds=30)
_WORKSPACE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=2,
    backoff_coefficient=2.0,
)


@workflow.defn(name="BidWorkflow")
class BidWorkflow:
    """Durable orchestration for the full bid pipeline (S0..S11)."""

    def __init__(self) -> None:
        self._state: WorkflowState = "S0"
        self._bid_card: BidCard | None = None
        self._triage: TriageDecision | None = None
        self._scoping: ScopingResult | None = None
        self._profile: str | None = None
        self._signal: HumanTriageSignal | None = None
        self._ba_draft: BusinessRequirementsDraft | None = None
        self._sa_draft: SolutionArchitectureDraft | None = None
        self._domain_notes: DomainNotes | None = None
        self._convergence: ConvergenceReport | None = None
        self._hld: HLDDraft | None = None
        self._wbs: WBSDraft | None = None
        self._pricing: PricingDraft | None = None
        self._proposal_package: ProposalPackage | None = None
        self._reviews: list[ReviewRecord] = []
        self._submission: SubmissionRecord | None = None
        self._retrospective: RetrospectiveDraft | None = None

    @workflow.signal(name="human_triage_decision")
    def human_triage_decision(self, signal: HumanTriageSignal) -> None:
        """Gate resolver for S1 — called by NestJS when reviewer approves/rejects."""
        self._signal = signal

    @workflow.query(name="get_state")
    def get_state(self) -> BidState:
        """Snapshot used by NestJS polling + frontend viewer."""
        bid_id = self._bid_card.bid_id if self._bid_card else _NIL_UUID
        now = workflow.now()
        return BidState(
            bid_id=bid_id,
            current_state=self._state,
            bid_card=self._bid_card,
            triage=self._triage,
            scoping=self._scoping,
            profile=self._profile,  # type: ignore[arg-type]
            ba_draft=self._ba_draft,
            sa_draft=self._sa_draft,
            domain_notes=self._domain_notes,
            convergence=self._convergence,
            hld=self._hld,
            wbs=self._wbs,
            pricing=self._pricing,
            proposal_package=self._proposal_package,
            reviews=list(self._reviews),
            submission=self._submission,
            retrospective=self._retrospective,
            created_at=now,
            updated_at=now,
        )

    @workflow.run
    async def run(self, wf_input: BidWorkflowInput) -> BidState:
        await self._run_s0(wf_input)
        await self._snapshot_workspace("S0_DONE")
        await self._run_s1_triage()
        await self._snapshot_workspace("S1_DONE")

        gate_ok = await self._wait_human_gate()
        if not gate_ok:
            await self._snapshot_workspace("S1_NO_BID")
            return self._snapshot()

        await self._run_s2_scoping()
        await self._snapshot_workspace("S2_DONE")
        await self._run_s3_streams()
        await self._snapshot_workspace("S3_DONE")
        await self._run_s4_convergence()
        await self._snapshot_workspace("S4_DONE")
        await self._run_s5_solution_design()
        await self._snapshot_workspace("S5_DONE")
        await self._run_s6_wbs()
        await self._snapshot_workspace("S6_DONE")
        await self._run_s7_commercial()
        await self._snapshot_workspace("S7_DONE")
        await self._run_s8_assembly()
        await self._snapshot_workspace("S8_DONE")
        await self._run_s9_review()
        await self._snapshot_workspace("S9_DONE")
        await self._run_s10_submission()
        await self._snapshot_workspace("S10_DONE")
        await self._run_s11_retrospective()

        self._state = "S11_DONE"
        await self._snapshot_workspace("S11_DONE")
        return self._snapshot()

    # --- S0 / S1 / S2 (Phase 1 logic — kept intact) --------------------------

    async def _run_s0(self, wf_input: BidWorkflowInput) -> None:
        self._state = "S0"
        if wf_input.prebuilt_card is not None:
            self._bid_card = wf_input.prebuilt_card
        elif wf_input.intake is not None:
            self._bid_card = await workflow.execute_activity(
                intake_activity,
                wf_input.intake,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=_DEFAULT_RETRY,
            )
        else:
            raise workflow.ApplicationError(
                "BidWorkflowInput requires exactly one of `intake` or `prebuilt_card`.",
                non_retryable=True,
            )

    async def _run_s1_triage(self) -> None:
        assert self._bid_card is not None
        self._state = "S1"
        self._triage = await workflow.execute_activity(
            triage_activity,
            self._bid_card,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _wait_human_gate(self) -> bool:
        """Wait for reviewer signal; return True only if approved."""
        try:
            await workflow.wait_condition(
                lambda: self._signal is not None, timeout=HUMAN_GATE_TIMEOUT
            )
        except TimeoutError:
            self._state = "S1_NO_BID"
            workflow.logger.info("bid.no_bid reason=human gate timeout")
            return False

        assert self._signal is not None
        if not self._signal.approved:
            self._state = "S1_NO_BID"
            workflow.logger.info(
                "bid.no_bid reason=%s", self._signal.notes or "rejected by reviewer"
            )
            return False

        assert self._bid_card is not None
        self._profile = (
            self._signal.bid_profile_override or self._bid_card.estimated_profile
        )
        self._bid_card = self._bid_card.model_copy(
            update={"estimated_profile": self._profile}
        )
        return True

    async def _run_s2_scoping(self) -> None:
        assert self._bid_card is not None
        self._state = "S2"
        self._scoping = await workflow.execute_activity(
            scoping_activity,
            self._bid_card,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )
        self._state = "S2_DONE"

    # --- S3 parallel streams -------------------------------------------------

    async def _run_s3_streams(self) -> None:
        assert self._bid_card is not None and self._scoping is not None
        self._state = "S3"

        stream_input = StreamInput(
            bid_id=self._bid_card.bid_id,
            client_name=self._bid_card.client_name,
            industry=self._bid_card.industry,
            region=self._bid_card.region,
            requirements=self._scoping.requirement_map,
            constraints=[],
            deadline=self._bid_card.deadline,
        )

        ba_future = workflow.execute_activity(
            ba_analysis_activity,
            stream_input,
            start_to_close_timeout=S3_ACTIVITY_TIMEOUT,
            heartbeat_timeout=S3_HEARTBEAT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )
        sa_future = workflow.execute_activity(
            sa_analysis_activity,
            stream_input,
            start_to_close_timeout=S3_ACTIVITY_TIMEOUT,
            heartbeat_timeout=S3_HEARTBEAT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )
        dm_future = workflow.execute_activity(
            domain_mining_activity,
            stream_input,
            start_to_close_timeout=S3_ACTIVITY_TIMEOUT,
            heartbeat_timeout=S3_HEARTBEAT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        self._ba_draft, self._sa_draft, self._domain_notes = await asyncio.gather(
            ba_future, sa_future, dm_future
        )

    # --- S4..S11 sequential downstream --------------------------------------

    async def _run_s4_convergence(self) -> None:
        assert self._ba_draft and self._sa_draft and self._domain_notes and self._bid_card
        self._state = "S4"
        self._convergence = await workflow.execute_activity(
            convergence_activity,
            ConvergenceInput(
                bid_id=self._bid_card.bid_id,
                ba_draft=self._ba_draft,
                sa_draft=self._sa_draft,
                domain_notes=self._domain_notes,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _run_s5_solution_design(self) -> None:
        assert self._convergence and self._sa_draft and self._bid_card
        self._state = "S5"
        self._hld = await workflow.execute_activity(
            solution_design_activity,
            SolutionDesignInput(
                bid_id=self._bid_card.bid_id,
                convergence=self._convergence,
                sa_draft=self._sa_draft,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _run_s6_wbs(self) -> None:
        assert self._hld and self._ba_draft and self._bid_card
        self._state = "S6"
        self._wbs = await workflow.execute_activity(
            wbs_activity,
            WBSInput(
                bid_id=self._bid_card.bid_id,
                hld=self._hld,
                ba_draft=self._ba_draft,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _run_s7_commercial(self) -> None:
        assert self._wbs and self._bid_card
        self._state = "S7"
        self._pricing = await workflow.execute_activity(
            commercial_activity,
            CommercialInput(
                bid_id=self._bid_card.bid_id,
                wbs=self._wbs,
                industry=self._bid_card.industry,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _run_s8_assembly(self) -> None:
        assert (
            self._ba_draft
            and self._sa_draft
            and self._domain_notes
            and self._hld
            and self._wbs
            and self._pricing
            and self._bid_card
        )
        self._state = "S8"
        self._proposal_package = await workflow.execute_activity(
            assembly_activity,
            AssemblyInput(
                bid_id=self._bid_card.bid_id,
                title=f"Proposal for {self._bid_card.client_name}",
                ba_draft=self._ba_draft,
                sa_draft=self._sa_draft,
                domain_notes=self._domain_notes,
                hld=self._hld,
                wbs=self._wbs,
                pricing=self._pricing,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _run_s9_review(self) -> None:
        assert self._proposal_package and self._bid_card
        self._state = "S9"
        record = await workflow.execute_activity(
            review_activity,
            ReviewInput(
                bid_id=self._bid_card.bid_id,
                package=self._proposal_package,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )
        self._reviews.append(record)

    async def _run_s10_submission(self) -> None:
        assert self._proposal_package and self._bid_card
        self._state = "S10"
        self._submission = await workflow.execute_activity(
            submission_activity,
            SubmissionInput(
                bid_id=self._bid_card.bid_id,
                package=self._proposal_package,
                reviews=list(self._reviews),
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    async def _run_s11_retrospective(self) -> None:
        assert self._submission and self._bid_card
        self._state = "S11"
        self._retrospective = await workflow.execute_activity(
            retrospective_activity,
            RetrospectiveInput(
                bid_id=self._bid_card.bid_id,
                submission=self._submission,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

    # --- helpers ------------------------------------------------------------

    async def _snapshot_workspace(self, phase: str) -> None:
        """Best-effort per-phase vault write. Failures are logged, never fatal."""
        if self._bid_card is None:
            return
        try:
            await workflow.execute_activity(
                workspace_snapshot_activity,
                WorkspaceInput(
                    vault_root="",  # activity falls back to KB_VAULT_PATH
                    phase=phase,
                    bid_state=self._snapshot(),
                ),
                start_to_close_timeout=_WORKSPACE_TIMEOUT,
                retry_policy=_WORKSPACE_RETRY,
            )
        except Exception as exc:  # noqa: BLE001 — vault issues never block the workflow
            workflow.logger.warning(
                "workspace_snapshot.ignored phase=%s err=%s", phase, exc
            )

    def _snapshot(self) -> BidState:
        """Materialise the current snapshot (used by `run` return + NO_BID path)."""
        bid_id = self._bid_card.bid_id if self._bid_card else _NIL_UUID
        now = workflow.now()
        return BidState(
            bid_id=bid_id,
            current_state=self._state,
            bid_card=self._bid_card,
            triage=self._triage,
            scoping=self._scoping if self._state != "S1_NO_BID" else None,
            profile=self._profile if self._state != "S1_NO_BID" else None,  # type: ignore[arg-type]
            ba_draft=self._ba_draft,
            sa_draft=self._sa_draft,
            domain_notes=self._domain_notes,
            convergence=self._convergence,
            hld=self._hld,
            wbs=self._wbs,
            pricing=self._pricing,
            proposal_package=self._proposal_package,
            reviews=list(self._reviews),
            submission=self._submission,
            retrospective=self._retrospective,
            created_at=now,
            updated_at=now,
        )
