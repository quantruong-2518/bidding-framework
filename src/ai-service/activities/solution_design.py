"""S5 Solution Design activity — Temporal wrapper around the HLD agent.

Falls back to the Phase 2.1 deterministic skeleton when no LLM provider is
available or when the agent produces unparseable output. The wrapper always
returns a well-formed :class:`HLDDraft` so S6 / S8 never see None.
"""

from __future__ import annotations

import logging

from temporalio import activity

from agents.solution_design_agent import run_solution_design_agent
from config.llm import is_llm_available
from tools.langfuse_client import get_tracer, span_context as langfuse_span_context
from workflows.artifacts import (
    HLDComponent,
    HLDDraft,
    SolutionDesignInput,
)

logger = logging.getLogger(__name__)


def _solution_design_stub(payload: SolutionDesignInput) -> HLDDraft:
    """Phase 2.1 deterministic baseline — preserved as the fallback contract."""
    components = [
        HLDComponent(
            name=f"{choice.layer} Layer",
            responsibility=choice.rationale,
            depends_on=[],
        )
        for choice in payload.sa_draft.tech_stack
    ]
    for idx in range(1, len(components)):
        components[idx - 1].depends_on.append(components[idx].name)
    data_flows = [
        "Client request → API gateway → service → datastore",
        "Event bus fan-out for audit + analytics",
    ]
    integration_points = list(payload.sa_draft.integrations) or [
        "Identity provider",
        "Data warehouse",
    ]
    return HLDDraft(
        bid_id=payload.bid_id,
        architecture_overview=(
            "Layered architecture derived from the SA stream. "
            f"{payload.convergence.unified_summary}"
        ),
        components=components,
        data_flows=data_flows,
        integration_points=integration_points,
        security_approach=(
            "Defence in depth: edge gateway, service-level auth, encrypted datastore."
        ),
        deployment_model="Kubernetes rolling deploy with feature-flagged canaries.",
    )


@activity.defn(name="solution_design_activity")
async def solution_design_activity(payload: SolutionDesignInput) -> HLDDraft:
    """Synthesise an HLD from the convergence + SA draft (real LLM or stub)."""
    if not is_llm_available():
        activity.logger.info(
            "solution_design.fallback_to_stub bid_id=%s", payload.bid_id
        )
        return _solution_design_stub(payload)

    activity.logger.info(
        "solution_design.start bid_id=%s sa_layers=%d integrations=%d",
        payload.bid_id,
        len(payload.sa_draft.tech_stack),
        len(payload.sa_draft.integrations),
    )
    activity.heartbeat("solution_design_started")

    tracer = get_tracer()
    span = tracer.start_span(
        trace_id=str(payload.bid_id),
        name="solution_design",
        metadata={
            "attempt": activity.info().attempt,
            "tier": "flagship+small",
        },
    )
    try:
        async with langfuse_span_context(span):
            draft = await run_solution_design_agent(payload)
    except Exception as exc:  # noqa: BLE001 — any agent failure → stub fallback
        activity.logger.warning(
            "solution_design.agent_failed_using_stub bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        draft = _solution_design_stub(payload)
    finally:
        span.end()
        await tracer.aclose()

    activity.heartbeat("solution_design_completed")
    activity.logger.info(
        "solution_design.done bid_id=%s components=%d integrations=%d cost_usd=%.6f",
        payload.bid_id,
        len(draft.components),
        len(draft.integration_points),
        draft.llm_cost_usd or 0.0,
    )
    return draft
