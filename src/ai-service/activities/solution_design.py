"""S5 Solution Design activity (Phase 2.1 stub)."""

from __future__ import annotations

import logging

from temporalio import activity

from workflows.artifacts import HLDComponent, HLDDraft, SolutionDesignInput

logger = logging.getLogger(__name__)


@activity.defn(name="solution_design_activity")
async def solution_design_activity(payload: SolutionDesignInput) -> HLDDraft:
    """Synthesise an HLD skeleton from SA draft + convergence report."""
    activity.logger.info("solution_design.start bid_id=%s", payload.bid_id)

    components = [
        HLDComponent(
            name=f"{choice.layer} Layer",
            responsibility=choice.rationale,
            depends_on=[],
        )
        for choice in payload.sa_draft.tech_stack
    ]
    # Simple linear dependency chain — top layer depends on the one below it.
    for idx in range(1, len(components)):
        components[idx - 1].depends_on.append(components[idx].name)

    data_flows = [
        "Client request → API gateway → service → datastore",
        "Event bus fan-out for audit + analytics",
    ]
    integration_points = list(payload.sa_draft.integrations) or ["Identity provider", "Data warehouse"]

    hld = HLDDraft(
        bid_id=payload.bid_id,
        architecture_overview=(
            "Layered architecture derived from the SA stream. "
            f"{payload.convergence.unified_summary}"
        ),
        components=components,
        data_flows=data_flows,
        integration_points=integration_points,
        security_approach="Defence in depth: edge gateway, service-level auth, encrypted datastore.",
        deployment_model="Kubernetes rolling deploy with feature-flagged canaries.",
    )
    activity.logger.info(
        "solution_design.done bid_id=%s components=%d",
        payload.bid_id,
        len(components),
    )
    return hld
