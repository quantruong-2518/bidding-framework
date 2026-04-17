"""FastAPI router — thin HTTP surface for starting/signaling/querying bid workflows."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from config.temporal import get_settings, get_temporal_client
from workflows.models import (
    BidCard,
    BidState,
    BidWorkflowInput,
    HumanTriageSignal,
    IntakeInput,
    StartWorkflowResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows/bid", tags=["workflows"])

WORKFLOW_ID_PREFIX = "bid-"


async def _start_workflow(wf_input: BidWorkflowInput) -> StartWorkflowResponse:
    from workflows.bid_workflow import BidWorkflow  # lazy: avoids temporal import at boot

    settings = get_settings()
    client = await get_temporal_client()

    workflow_id = f"{WORKFLOW_ID_PREFIX}{uuid4()}"
    handle = await client.start_workflow(
        BidWorkflow.run,
        wf_input,
        id=workflow_id,
        task_queue=settings.task_queue,
    )
    logger.info("workflow.started id=%s run=%s", handle.id, handle.result_run_id)
    return StartWorkflowResponse(
        workflow_id=handle.id,
        run_id=handle.result_run_id,
        task_queue=settings.task_queue,
    )


@router.post("/start", response_model=StartWorkflowResponse)
async def start_bid_workflow(payload: IntakeInput) -> StartWorkflowResponse:
    """Start from raw RFP metadata — runs S0 to extract BidCard."""
    return await _start_workflow(BidWorkflowInput(intake=payload))


@router.post("/start-from-card", response_model=StartWorkflowResponse)
async def start_bid_workflow_from_card(card: BidCard) -> StartWorkflowResponse:
    """Start with a pre-built BidCard — skips S0 when upstream already has structured fields."""
    return await _start_workflow(BidWorkflowInput(prebuilt_card=card))


@router.post("/{workflow_id}/triage-signal", status_code=202)
async def send_triage_signal(workflow_id: str, signal: HumanTriageSignal) -> dict[str, str]:
    """Forward the human gate decision to the running workflow."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.signal("human_triage_decision", signal)
    except Exception as exc:  # noqa: BLE001 — surface any Temporal error as 404/500
        logger.exception("signal.error workflow=%s", workflow_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "accepted", "workflow_id": workflow_id}


@router.get("/{workflow_id}", response_model=BidState)
async def get_bid_state(workflow_id: str) -> BidState:
    """Query the workflow for its latest BidState snapshot."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        return await handle.query("get_state")
    except Exception as exc:  # noqa: BLE001
        logger.exception("query.error workflow=%s", workflow_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
