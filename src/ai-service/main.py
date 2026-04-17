"""AI Service — FastAPI entrypoint.

Hosts the Temporal worker registration entrypoints, RAG endpoints, and health
probes. Business logic lives in `workflows/`, `activities/`, `agents/`, `rag/`,
and `ingestion/` — this file only wires them up.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="AI Bidding Framework — AI Service",
    version="0.1.0",
    description="Python FastAPI + Temporal workers + LangGraph agents",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by Docker Compose healthcheck."""
    return {"status": "ok", "service": "ai-service"}


# --- Task 1.2: Workflow router ---
# Mounts POST /workflows/bid/start, POST /workflows/bid/{id}/triage-signal, GET /workflows/bid/{id}.
# Kept at the bottom of main.py so the module boots even if Temporal is briefly unavailable
# at FastAPI startup; the client connects lazily per-request inside the router.
from workflows.router import router as bid_workflow_router  # noqa: E402

app.include_router(bid_workflow_router)
# --- End Task 1.2 ---
