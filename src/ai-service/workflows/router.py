"""FastAPI router — thin HTTP surface for starting/signaling/querying bid workflows."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from config.temporal import get_settings, get_temporal_client
from parsers import docx_adapter, pypdf_adapter, rfp_extractor
from parsers.models import ParseResponse
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


MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB — Word/PDF RFPs rarely exceed this


def _dispatch_parser(filename: str, data: bytes) -> ParseResponse:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        parsed = pypdf_adapter.parse_pdf_bytes(data, filename)
    elif name.endswith(".docx"):
        parsed = docx_adapter.parse_docx_bytes(data, filename)
    else:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file extension for {filename!r}; upload .pdf or .docx",
        )
    suggestion = rfp_extractor.extract_bid_card(parsed)
    return ParseResponse(parsed_rfp=parsed, suggested_bid_card=suggestion)


@router.post("/parse-rfp", response_model=ParseResponse)
async def parse_rfp(file: UploadFile = File(...)) -> ParseResponse:
    """Parse an uploaded RFP (PDF or DOCX) into a ParsedRFP + BidCard suggestion.

    The frontend pre-fills the "Create bid" form with the suggestion; the bid
    manager reviews + edits before hitting `/start-from-card`.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB upload limit.",
        )
    try:
        response = _dispatch_parser(file.filename or "", data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — malformed binaries bubble up here
        logger.exception("parse_rfp.failed file=%s", file.filename)
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc
    logger.info(
        "parse_rfp.done file=%s sections=%d reqs=%d",
        file.filename,
        len(response.parsed_rfp.sections),
        len(response.suggested_bid_card.requirement_candidates),
    )
    return response


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
