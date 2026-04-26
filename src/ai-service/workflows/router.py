"""FastAPI router — thin HTTP surface for starting/signaling/querying bid workflows."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from config.temporal import get_settings, get_temporal_client
from parsers import docx_adapter, pypdf_adapter, rfp_extractor
from parsers.models import ParseResponse
from workflows.acl import acl_as_json, apply_role_filter
from workflows.base import IntakeFile
from workflows.models import (
    BidCard,
    BidState,
    BidWorkflowInput,
    HumanReviewSignal,
    HumanTriageSignal,
    IntakeInput,
    StartWorkflowResponse,
)

def _parse_roles_header(raw: str | None) -> list[str]:
    """Split the trusted ``x-user-roles`` header into a deduped role list."""

    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]

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


@router.post("/{workflow_id}/review-signal", status_code=202)
async def send_review_signal(
    workflow_id: str, signal: HumanReviewSignal
) -> dict[str, str]:
    """Forward a S9 human review decision to the running workflow."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.signal("human_review_decision", signal)
    except Exception as exc:  # noqa: BLE001
        logger.exception("review_signal.error workflow=%s", workflow_id)
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


@router.get("/acl/artifacts")
async def get_artifact_acl() -> dict[str, list[str]]:
    """Return the artifact-key → allowed-role map.

    Public (auth-enforced upstream in NestJS). The frontend caches the response
    after login so every dashboard render can filter panels client-side without
    a round-trip.
    """

    return acl_as_json()


# ---------------------------------------------------------------------------
# Wave 2A — multi-file parse + materialize endpoints.
#
# These run OUTSIDE Temporal (per Decision #9): the parse-confirm gate must
# stay fast and re-runnable, with no ghost workflows on abandoned uploads.
# We launch a background asyncio.task per parse, store result in an in-memory
# tracker, and POST it back to api-gateway when ready.
# ---------------------------------------------------------------------------


class _ParseStartRequest(BaseModel):
    parse_session_id: str
    files: list[IntakeFile] = Field(default_factory=list)
    tenant_id: str
    lang: Literal["en", "vi"] = "en"
    callback_url: str | None = None  # optional — POST result back when ready


class _ParseStatus(BaseModel):
    status: Literal["PARSING", "READY", "FAILED"]
    session_id: str
    progress: dict[str, Any] | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


# Module-level in-memory tracker. Sufficient for v1 — a parse session lives
# in api-gateway's parse_sessions row anyway, so this is just a coarse
# "is the worker still chewing?" cache surfaced via GET /parse/:sid/status.
# Concurrency: only the background task writes; the GET reads. Reads happen
# inside the FastAPI loop so a GIL-protected dict is fine.
_PARSE_TRACKER: dict[str, _ParseStatus] = {}


class _ParseMaterializeRequest(BaseModel):
    bid_id: str
    tenant_id: str
    parse_session_payload: dict[str, Any] = Field(default_factory=dict)
    vault_root: str = ""


async def _run_parse_in_background(req: _ParseStartRequest) -> None:
    """Long-running task spawned by POST /parse/start. Updates tracker + posts."""
    from activities.context_synthesis import (
        ContextSynthesisInput,
        _run_preview,
    )

    sid = req.parse_session_id
    _PARSE_TRACKER[sid] = _ParseStatus(
        status="PARSING",
        session_id=sid,
        progress={"stage": "starting", "percent": 0},
    )
    try:
        out = await _run_preview(
            ContextSynthesisInput(
                mode="preview",
                parse_session_id=sid,
                tenant_id=req.tenant_id,
                lang=req.lang,
                files=req.files,
            )
        )
        result_payload = out.model_dump(mode="json")
        _PARSE_TRACKER[sid] = _ParseStatus(
            status="READY", session_id=sid, result=result_payload
        )
        if req.callback_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    await client.post(req.callback_url, json=result_payload)
            except Exception as exc:  # noqa: BLE001 — tracker still valid
                logger.warning(
                    "parse.callback_failed sid=%s url=%s err=%s",
                    sid,
                    req.callback_url,
                    exc,
                )
    except Exception as exc:  # noqa: BLE001 — surface to tracker
        logger.exception("parse.background_failed sid=%s", sid)
        _PARSE_TRACKER[sid] = _ParseStatus(
            status="FAILED", session_id=sid, error=str(exc)[:500]
        )


@router.post("/parse/start", status_code=202)
async def start_parse_session(req: _ParseStartRequest) -> dict[str, str]:
    """Kick off a multi-file parse asynchronously.

    Returns immediately with ``{status: "PARSING", session_id}``. The actual
    LLM-driven parse runs in a background task; results land in the tracker
    + are POSTed to ``callback_url`` if supplied.
    """
    asyncio.create_task(_run_parse_in_background(req))
    return {"status": "PARSING", "session_id": req.parse_session_id}


@router.get("/parse/{session_id}/status", response_model=_ParseStatus)
async def get_parse_status(session_id: str) -> _ParseStatus:
    """Return the in-memory parse status for a session."""
    record = _PARSE_TRACKER.get(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown session_id={session_id}")
    return record


@router.post("/parse/{session_id}/materialize")
async def materialize_parse_session(
    session_id: str, req: _ParseMaterializeRequest
) -> dict[str, Any]:
    """Materialize a confirmed parse session into the bid vault.

    Called by api-gateway inside its atomic confirm transaction (Decision #11).
    Synchronous — caller awaits the vault write before committing.
    """
    from activities.context_synthesis import ContextSynthesisInput, _run_materialize

    out = await _run_materialize(
        ContextSynthesisInput(
            mode="materialize",
            parse_session_id=session_id,
            tenant_id=req.tenant_id,
            bid_id=req.bid_id,
            payload=req.parse_session_payload,
            vault_root=req.vault_root,
            files=[],
        )
    )
    return {
        "bid_id": req.bid_id,
        "vault_path": req.vault_root or "../kb-vault",
        "files_written": out.files_written,
        "atoms_written": len(out.atoms),
    }


@router.get("/{workflow_id}", response_model=BidState)
async def get_bid_state(
    workflow_id: str,
    x_user_roles: str | None = Header(default=None, alias="x-user-roles"),
) -> BidState:
    """Query the workflow for its latest BidState snapshot.

    When ``x-user-roles`` is supplied by the api-gateway, role-gated artifact
    fields not visible to the caller are scrubbed to ``None`` (or ``[]`` for
    ``reviews``) before the snapshot is returned. Missing header → no filter
    (trusts internal callers).
    """

    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        state: BidState = await handle.query("get_state")
    except Exception as exc:  # noqa: BLE001
        logger.exception("query.error workflow=%s", workflow_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return apply_role_filter(state, _parse_roles_header(x_user_roles))
