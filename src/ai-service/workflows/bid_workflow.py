"""Temporal workflow: S0 Intake -> S1 Triage (human gate) -> S2 Scoping."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

_NIL_UUID = UUID(int=0)

with workflow.unsafe.imports_passed_through():
    from activities.intake import intake_activity
    from activities.scoping import scoping_activity
    from activities.triage import triage_activity
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

_DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)


@workflow.defn(name="BidWorkflow")
class BidWorkflow:
    """S0 -> S1 (human gate) -> S2. Later waves extend from S2_DONE onward."""

    def __init__(self) -> None:
        self._state: WorkflowState = "S0"
        self._bid_card: BidCard | None = None
        self._triage: TriageDecision | None = None
        self._scoping: ScopingResult | None = None
        self._profile: str | None = None
        self._signal: HumanTriageSignal | None = None

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
            created_at=now,
            updated_at=now,
        )

    @workflow.run
    async def run(self, wf_input: BidWorkflowInput) -> BidState:
        # --- S0 Intake ---------------------------------------------------
        self._state = "S0"
        if wf_input.prebuilt_card is not None:
            # Upstream already produced a BidCard (e.g., UI-entered structured fields) — skip RFP parsing.
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

        # --- S1 Triage (AI score) ---------------------------------------
        self._state = "S1"
        self._triage = await workflow.execute_activity(
            triage_activity,
            self._bid_card,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        # --- S1 Gate (human signal) -------------------------------------
        try:
            await workflow.wait_condition(
                lambda: self._signal is not None, timeout=HUMAN_GATE_TIMEOUT
            )
        except TimeoutError:
            self._state = "S1_NO_BID"
            return self._finalize_no_bid(reason="human gate timeout")

        assert self._signal is not None
        if not self._signal.approved:
            self._state = "S1_NO_BID"
            return self._finalize_no_bid(reason=self._signal.notes or "rejected by reviewer")

        # Profile lock: reviewer may override AI's estimate.
        self._profile = (
            self._signal.bid_profile_override or self._bid_card.estimated_profile
        )
        # Normalised card — keep original estimate but use agreed profile downstream.
        scoping_card = self._bid_card.model_copy(
            update={"estimated_profile": self._profile}
        )

        # --- S2 Scoping -------------------------------------------------
        self._state = "S2"
        self._scoping = await workflow.execute_activity(
            scoping_activity,
            scoping_card,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        self._state = "S2_DONE"
        now = workflow.now()
        return BidState(
            bid_id=self._bid_card.bid_id,
            current_state=self._state,
            bid_card=self._bid_card,
            triage=self._triage,
            scoping=self._scoping,
            profile=self._profile,  # type: ignore[arg-type]
            created_at=now,
            updated_at=now,
        )

    def _finalize_no_bid(self, reason: str) -> BidState:
        """Return the terminal NO_BID snapshot; reason is logged for audit."""
        workflow.logger.info("bid.no_bid reason=%s", reason)
        assert self._bid_card is not None
        now = workflow.now()
        return BidState(
            bid_id=self._bid_card.bid_id,
            current_state="S1_NO_BID",
            bid_card=self._bid_card,
            triage=self._triage,
            scoping=None,
            profile=None,
            created_at=now,
            updated_at=now,
        )


