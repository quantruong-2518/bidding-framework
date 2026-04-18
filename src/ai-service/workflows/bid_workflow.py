"""Temporal workflow — full 11-state DAG.

Order: S0 Intake -> S1 Triage (+ human gate) -> S2 Scoping ->
       S3 parallel (S3a BA / S3b SA / S3c Domain) -> S4 Convergence ->
       S5 Solution Design -> S6 WBS -> S7 Commercial -> S8 Assembly ->
       S9 Review Gate (Phase 2.4 human signal + loop-back) ->
       S10 Submission -> S11 Retrospective -> S11_DONE.

Phase 2.2: S3a/b/c call the real LangGraph-backed activities.
Phase 2.6: declarative `_PROFILE_PIPELINE` drives the iteration; Bid-S
skips S5 + S7.
Phase 2.4: S9 runs a real signal-based review gate with sequential
multi-reviewer, per-profile timeout, 3-round cap, earliest-target
loop-back, and best-effort `approval_needed` notification.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.base import BidProfile

_NIL_UUID = UUID(int=0)

# Phase 2.6 declarative pipeline matrix.
# Bid-S skips S5 (Solution Design) + S7 (Commercial) — minimal fast-path.
# Bid-M / L / XL run the full 12-state pipeline. XL parity (S3d/S3e) deferred.
_PROFILE_PIPELINE: dict[BidProfile, tuple[str, ...]] = {
    "S": ("S0", "S1", "S2", "S3", "S4", "S6", "S8", "S9", "S10", "S11"),
    "M": ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11"),
    "L": ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11"),
    "XL": ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11"),
}

# State literal → BidWorkflow method attribute name. Populated at class body
# time by walking this tuple; keeping it module-level keeps `workflow.unsafe`
# imports out of the critical path.
_STATE_DISPATCH_MAP: dict[str, str] = {
    "S2": "_run_s2_scoping",
    "S3": "_run_s3_streams",
    "S4": "_run_s4_convergence",
    "S5": "_run_s5_solution_design",
    "S6": "_run_s6_wbs",
    "S7": "_run_s7_commercial",
    "S8": "_run_s8_assembly",
    "S9": "_run_s9_review_gate",
    "S10": "_run_s10_submission",
    "S11": "_run_s11_retrospective",
}

# --- Phase 2.4 S9 human review gate knobs -----------------------------------
# Per-profile signal timeout per reviewer — defaults in plan (72h / 120h XL).
_S9_TIMEOUT: dict[BidProfile, timedelta] = {
    "S": timedelta(hours=72),
    "M": timedelta(hours=72),
    "L": timedelta(hours=72),
    "XL": timedelta(hours=120),
}

# How many reviewers must sign off per round. Parallel concurrent is Phase 3;
# for now run sequentially — any REJECT / CHANGES_REQUESTED short-circuits
# the rest of the round.
_S9_REVIEWER_COUNT: dict[BidProfile, int] = {
    "S": 1,
    "M": 1,
    "L": 3,
    "XL": 5,
}

_MAX_REVIEW_ROUNDS = 3

# Explicit ordering of valid loop-back targets (earliest-first). Used for
# aggregation when a reviewer's comments name multiple target_states.
_LOOP_BACK_ORDER: tuple[str, ...] = ("S2", "S5", "S6", "S8")

# Declarative white-list mapping: on loop-back to <target>, these
# BidWorkflow attribute names must be reset to their initial value so
# downstream artifacts don't leak from a stale round.
_ARTIFACT_CLEANUP: dict[str, tuple[str, ...]] = {
    "S2": (
        "_scoping",
        "_ba_draft",
        "_sa_draft",
        "_domain_notes",
        "_convergence",
        "_hld",
        "_wbs",
        "_pricing",
        "_proposal_package",
    ),
    "S5": ("_hld", "_wbs", "_pricing", "_proposal_package"),
    "S6": ("_wbs", "_pricing", "_proposal_package"),
    "S8": ("_proposal_package",),
}

with workflow.unsafe.imports_passed_through():
    from activities.assembly import assembly_activity
    from activities.ba_analysis import ba_analysis_activity
    from activities.bid_workspace import workspace_snapshot_activity
    from activities.commercial import commercial_activity
    from activities.convergence import convergence_activity
    from activities.domain_mining import domain_mining_activity
    from activities.intake import intake_activity
    from activities.notify import (
        NotifyApprovalInput,
        notify_approval_needed_activity,
    )
    from activities.retrospective import retrospective_activity
    from activities.review import review_activity
    from activities.sa_analysis import sa_analysis_activity
    from activities.scoping import scoping_activity
    from activities.solution_design import solution_design_activity
    from activities.state_transition import (
        NotifyStateTransitionInput,
        state_transition_activity,
    )
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
        ReviewComment,
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
        HumanReviewSignal,
        HumanTriageSignal,
        LoopBack,
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

# Phase 2.5 — which BidState fields were written during each phase. Published
# alongside `state_completed` events so the frontend can refetch only the
# affected artifacts (or render a "+3 artifacts" hint).
_PHASE_ARTIFACT_KEYS: dict[str, tuple[str, ...]] = {
    "S0_DONE": ("bid_card",),
    "S1_DONE": ("triage",),
    "S1_NO_BID": (),
    "S2_DONE": ("scoping",),
    "S3_DONE": ("ba_draft", "sa_draft", "domain_notes"),
    "S4_DONE": ("convergence",),
    "S5_DONE": ("hld",),
    "S6_DONE": ("wbs",),
    "S7_DONE": ("pricing",),
    "S8_DONE": ("proposal_package",),
    "S9_DONE": ("reviews",),
    "S10_DONE": ("submission",),
    "S11_DONE": ("retrospective",),
}


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
        # Phase 2.4 — S9 human review gate state. Signals queue up in order;
        # gate consumes one per reviewer per round via a monotonic cursor so
        # pre-delivered signals (e.g. in fast test envs) aren't dropped.
        self._review_signals: list[HumanReviewSignal] = []
        self._review_consumed: int = 0
        self._review_round: int = 0
        self._loop_back_history: list[LoopBack] = []

    @workflow.signal(name="human_triage_decision")
    def human_triage_decision(self, signal: HumanTriageSignal) -> None:
        """Gate resolver for S1 — called by NestJS when reviewer approves/rejects."""
        self._signal = signal

    @workflow.signal(name="human_review_decision")
    def human_review_decision(self, signal: HumanReviewSignal) -> None:
        """S9 reviewer signal — appended to FIFO queue; consumed by the gate."""
        self._review_signals.append(signal)

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
            loop_back_history=list(self._loop_back_history),
            created_at=now,
            updated_at=now,
        )

    @workflow.run
    async def run(self, wf_input: BidWorkflowInput) -> BidState:
        await self._run_s0(wf_input)
        await self._complete_phase("S0_DONE")
        await self._run_s1_triage()
        await self._complete_phase("S1_DONE")

        gate_ok = await self._wait_human_gate()
        if not gate_ok:
            await self._complete_phase("S1_NO_BID")
            return self._snapshot()

        profile: BidProfile = self._profile or "M"  # type: ignore[assignment]
        if profile == "XL":
            workflow.logger.info("XL_PARITY_PENDING phase=2.6")
        pipeline = _PROFILE_PIPELINE[profile]
        idx = pipeline.index("S2")
        while idx < len(pipeline):
            if self._state == "S9_BLOCKED":
                return self._snapshot()
            state = pipeline[idx]
            handler = getattr(self, _STATE_DISPATCH_MAP[state])
            await handler()
            await self._complete_phase(f"{state}_DONE")

            # Phase 2.4 loop-back: _run_s9_review may set self._state to an
            # earlier pipeline state. Detect + rewind. Phase 2.6 never triggers
            # this branch (review stub never loops back).
            if state == "S9" and self._state != "S9" and self._state in pipeline[:idx]:
                idx = pipeline.index(self._state)
                continue
            idx += 1

        if self._state == "S9_BLOCKED":
            return self._snapshot()
        self._state = "S11_DONE"
        # Terminal marker only — S11_DONE artifact event already fired when the
        # loop completed the "S11" phase; skip re-snapshot + re-notify to keep
        # the event stream free of duplicate terminal ticks.
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
        # hld may be None on Bid-S (S5 skipped) — wbs_activity tolerates it.
        assert self._ba_draft and self._bid_card
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
        # Bid-S skips S5 (HLD) + S7 (Pricing); the assembly stub null-guards
        # both (see activities/assembly.py).
        assert (
            self._ba_draft
            and self._sa_draft
            and self._domain_notes
            and self._wbs
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

    async def _run_s9_review_gate(self) -> None:
        """Phase 2.4 real review gate.

        Flow per round:
          1. Run pre-human AI review (`review_activity`) → appends a ReviewRecord
             flagging any consistency gaps.
          2. For each reviewer (per-profile count), emit `approval_needed`
             notification + wait for `human_review_decision` signal with
             per-profile timeout. Any REJECT / CHANGES_REQUESTED
             short-circuits remaining reviewers.
          3. Aggregate the round's verdict:
             - APPROVED by all reviewers → proceed (outer loop advances).
             - CHANGES_REQUESTED → compute earliest target_state, clear
               downstream artifacts, set `_state = target`, return.
             - REJECTED → terminal `S9_BLOCKED`.
          4. If round counter hits `_MAX_REVIEW_ROUNDS` without approval →
             `S9_BLOCKED`.
        """
        assert self._proposal_package and self._bid_card
        self._state = "S9"
        profile: BidProfile = self._profile or "M"  # type: ignore[assignment]

        pre_record = await workflow.execute_activity(
            review_activity,
            ReviewInput(
                bid_id=self._bid_card.bid_id,
                package=self._proposal_package,
            ),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )
        self._reviews.append(pre_record)

        round_idx = self._review_round + 1
        reviewer_count = _S9_REVIEWER_COUNT[profile]
        timeout = _S9_TIMEOUT[profile]
        final_verdict: str | None = None
        last_record: ReviewRecord | None = None

        for reviewer_idx in range(reviewer_count):
            await self._notify_approval_needed(
                round_idx=round_idx,
                reviewer_idx=reviewer_idx,
                reviewer_count=reviewer_count,
                profile=profile,
            )

            try:
                await workflow.wait_condition(
                    lambda: len(self._review_signals) > self._review_consumed,
                    timeout=timeout,
                )
            except TimeoutError:
                workflow.logger.info(
                    "s9.gate.timeout round=%d reviewer=%d/%d",
                    round_idx,
                    reviewer_idx + 1,
                    reviewer_count,
                )
                self._state = "S9_BLOCKED"
                self._review_round = round_idx
                return

            signal = self._review_signals[self._review_consumed]
            self._review_consumed += 1
            record = ReviewRecord(
                bid_id=self._bid_card.bid_id,
                reviewer_role=signal.reviewer_role,
                reviewer=signal.reviewer,
                verdict=signal.verdict,
                comments=list(signal.comments),
                reviewed_at=workflow.now(),
            )
            self._reviews.append(record)
            last_record = record
            final_verdict = signal.verdict

            if signal.verdict != "APPROVED":
                break

        self._review_round = round_idx

        if final_verdict == "REJECTED":
            self._state = "S9_BLOCKED"
            return

        if final_verdict == "CHANGES_REQUESTED":
            assert last_record is not None
            target = self._route_on_changes_requested(last_record, round_idx=round_idx)
            if target is None:
                # No valid target in the pipeline — degrade to S9_BLOCKED rather
                # than silently APPROVE (safer default).
                self._state = "S9_BLOCKED"
                return
            self._state = target  # type: ignore[assignment]
            if round_idx >= _MAX_REVIEW_ROUNDS:
                self._state = "S9_BLOCKED"
                return
            return

    def _route_on_changes_requested(
        self, record: ReviewRecord, round_idx: int
    ) -> str | None:
        """Pick earliest valid loop-back target + reset downstream artifacts.

        Returns the chosen target state, or None if no valid target survives
        the profile-pipeline check.
        """
        assert self._profile is not None
        profile: BidProfile = self._profile  # type: ignore[assignment]
        pipeline = _PROFILE_PIPELINE[profile]

        # Earliest-target aggregation (Q7). Default target = S8 (minor).
        ranks = {state: i for i, state in enumerate(_LOOP_BACK_ORDER)}
        candidates = [
            c.target_state for c in record.comments if c.target_state is not None
        ]
        if candidates:
            candidates.sort(key=lambda s: ranks.get(s, len(ranks)))
            chosen = candidates[0]
        else:
            chosen = "S8"

        # Fall forward to nearest pipeline-resident state if the chosen target
        # was skipped for this profile (e.g. S5 on Bid-S).
        if chosen not in pipeline:
            chosen_rank = ranks.get(chosen, 0)
            forward_candidates = [
                s
                for s in pipeline
                if s in _LOOP_BACK_ORDER and ranks[s] >= chosen_rank
            ]
            if not forward_candidates:
                return None
            chosen = forward_candidates[0]

        for attr in _ARTIFACT_CLEANUP.get(chosen, ()):
            setattr(self, attr, None)

        reason_bits = [
            f"[{c.severity}] {c.section}: {c.message}"
            for c in record.comments
        ]
        reason = " | ".join(reason_bits) if reason_bits else "changes requested"
        self._loop_back_history.append(
            LoopBack(
                round=round_idx,
                target_state=chosen,  # type: ignore[arg-type]
                reason=reason[:500],
                at=workflow.now(),
            )
        )
        workflow.logger.info(
            "s9.loopback round=%d target=%s reviewer=%s",
            round_idx,
            chosen,
            record.reviewer,
        )
        return chosen

    async def _notify_approval_needed(
        self,
        *,
        round_idx: int,
        reviewer_idx: int,
        reviewer_count: int,
        profile: BidProfile,
    ) -> None:
        """Best-effort WebSocket toast that an S9 gate is waiting on a human."""
        assert self._bid_card is not None
        try:
            await workflow.execute_activity(
                notify_approval_needed_activity,
                NotifyApprovalInput(
                    bid_id=str(self._bid_card.bid_id),
                    workflow_id=workflow.info().workflow_id,
                    state="S9",
                    profile=profile,
                    round=round_idx,
                    reviewer_index=reviewer_idx,
                    reviewer_count=reviewer_count,
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:  # noqa: BLE001 — notification is best-effort
            workflow.logger.warning("s9.notify.failed err=%s", exc)

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

    async def _notify_state_transition(
        self, phase: str, artifact_keys: tuple[str, ...]
    ) -> None:
        """Phase 2.5 best-effort broadcast that a phase just completed."""
        if self._bid_card is None:
            return
        profile: BidProfile = self._profile or self._bid_card.estimated_profile  # type: ignore[assignment]
        try:
            await workflow.execute_activity(
                state_transition_activity,
                NotifyStateTransitionInput(
                    bid_id=str(self._bid_card.bid_id),
                    state=phase,
                    profile=profile,
                    artifact_keys=list(artifact_keys),
                    occurred_at=workflow.now(),
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:  # noqa: BLE001 — notification is best-effort
            workflow.logger.warning(
                "state_transition.notify.failed phase=%s err=%s", phase, exc
            )

    async def _complete_phase(self, phase: str) -> None:
        """Run vault snapshot + emit the matching state_completed event.

        Emits events in snapshot-then-notify order so any subscriber re-fetching
        the bid's workspace artifacts observes read-your-writes (the vault file
        is already present when the WS event arrives).
        """
        await self._snapshot_workspace(phase)
        await self._notify_state_transition(
            phase, _PHASE_ARTIFACT_KEYS.get(phase, ())
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
            loop_back_history=list(self._loop_back_history),
            created_at=now,
            updated_at=now,
        )
