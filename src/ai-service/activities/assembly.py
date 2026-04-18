"""S8 Assembly activity — Phase 3.1 Jinja-backed proposal rendering.

Calls :func:`assembly.renderer.render_package` to produce all seven proposal
sections from the full bid context (BidCard + triage + scoping + BA/SA/Domain
+ HLD + WBS + pricing + convergence + reviews). On :class:`RendererError` the
activity falls back to the pre-3.1 hand-written stub sections so the bid
never fails on a templating glitch.
"""

from __future__ import annotations

import logging

from temporalio import activity

from assembly import RendererError, render_package
from workflows.artifacts import AssemblyInput, ProposalPackage, ProposalSection

logger = logging.getLogger(__name__)


def _stub_executive_section(payload: AssemblyInput) -> ProposalSection:
    price_line = (
        f"- Proposed price: {payload.pricing.total:.2f} {payload.pricing.currency}.\n"
        if payload.pricing is not None
        else "- Proposed price: TBD (Bid-S fast-path — commercial deferred to contract phase).\n"
    )
    body = (
        f"# Executive Summary\n\n"
        f"{payload.ba_draft.executive_summary}\n\n"
        f"- Total effort: {payload.wbs.total_effort_md:.1f} MD "
        f"over ~{payload.wbs.timeline_weeks} weeks.\n"
        f"{price_line}"
        f"- Architecture backbone: "
        f"{', '.join(ts.choice for ts in payload.sa_draft.tech_stack)}.\n"
    )
    return ProposalSection(
        heading="Executive Summary",
        body_markdown=body,
        sourced_from=["ba_draft", "wbs", "pricing", "sa_draft"],
    )


def _stub_solution_section(payload: AssemblyInput) -> ProposalSection:
    if payload.hld is None:
        overview = (
            "High-level design omitted for Bid-S fast-path. Solution shape "
            "derived directly from SA stream outputs."
        )
        tech_lines = "\n".join(
            f"- **{ts.layer}** — {ts.choice}: {ts.rationale}"
            for ts in payload.sa_draft.tech_stack
        )
        body = f"# Proposed Solution\n\n{overview}\n\n{tech_lines}\n"
        return ProposalSection(
            heading="Proposed Solution",
            body_markdown=body,
            sourced_from=["sa_draft"],
        )
    bullets = "\n".join(
        f"- **{c.name}** — {c.responsibility}" for c in payload.hld.components
    )
    body = f"# Proposed Solution\n\n{payload.hld.architecture_overview}\n\n{bullets}\n"
    return ProposalSection(
        heading="Proposed Solution",
        body_markdown=body,
        sourced_from=["hld", "sa_draft"],
    )


def _stub_delivery_section(payload: AssemblyInput) -> ProposalSection:
    phases = "\n".join(
        f"- {it.id} · {it.name} · {it.effort_md:.1f} MD" for it in payload.wbs.items
    )
    body = (
        f"# Delivery Plan\n\n{phases}\n\n"
        f"Critical path: {', '.join(payload.wbs.critical_path)}"
    )
    return ProposalSection(
        heading="Delivery Plan", body_markdown=body, sourced_from=["wbs"]
    )


def _stub_compliance_section(payload: AssemblyInput) -> ProposalSection:
    items = "\n".join(
        f"- **{c.framework}** — {c.requirement}"
        for c in payload.domain_notes.compliance
    )
    body = f"# Compliance + Domain Considerations\n\n{items}\n"
    return ProposalSection(
        heading="Compliance + Domain",
        body_markdown=body,
        sourced_from=["domain_notes"],
    )


def _stub_commercial_section(payload: AssemblyInput) -> ProposalSection:
    if payload.pricing is None:
        body = (
            "# Commercial Proposal\n\n"
            "Commercial terms deferred (Bid-S fast-path). Pricing will be "
            "negotiated at contract signature based on the WBS effort total.\n"
        )
        return ProposalSection(
            heading="Commercial", body_markdown=body, sourced_from=[]
        )
    lines = "\n".join(
        f"- {pl.label}: {pl.amount:.2f} {pl.unit}" for pl in payload.pricing.lines
    )
    body = (
        f"# Commercial Proposal\n\n"
        f"Model: {payload.pricing.model}. Currency: {payload.pricing.currency}.\n\n"
        f"{lines}\n\n"
        f"**Total: {payload.pricing.total:.2f} {payload.pricing.currency}** "
        f"(margin {payload.pricing.margin_pct:.1f}%)."
    )
    return ProposalSection(
        heading="Commercial", body_markdown=body, sourced_from=["pricing"]
    )


def _stub_fallback(payload: AssemblyInput, reason: str) -> ProposalPackage:
    """Pre-3.1 hand-written sections — used when Jinja rendering fails."""
    sections = [
        _stub_executive_section(payload),
        _stub_solution_section(payload),
        _stub_delivery_section(payload),
        _stub_compliance_section(payload),
        _stub_commercial_section(payload),
    ]
    consistency = {
        "has_executive_summary": True,
        "has_solution_section": True,
        "has_delivery_plan": bool(payload.wbs.items),
        "has_commercial_section": payload.pricing is None
        or bool(payload.pricing.lines),
        "compliance_covered": bool(payload.domain_notes.compliance),
        "rendered_all_sections": False,
        "template_error": True,
    }
    return ProposalPackage(
        bid_id=payload.bid_id,
        title=payload.title,
        sections=sections,
        appendices=["Assumptions (BA)", "Risk register (BA + SA)", f"Note: {reason}"],
        consistency_checks=consistency,
    )


@activity.defn(name="assembly_activity")
async def assembly_activity(payload: AssemblyInput) -> ProposalPackage:
    """Compile proposal sections — Jinja templates with a stub-fallback safety net."""
    activity.logger.info("assembly.start bid_id=%s", payload.bid_id)

    try:
        package = render_package(payload)
    except RendererError as exc:
        activity.logger.warning(
            "assembly.template_error bid_id=%s err=%s — falling back to stub",
            payload.bid_id,
            exc,
        )
        package = _stub_fallback(payload, reason=str(exc))

    activity.logger.info(
        "assembly.done bid_id=%s sections=%d rendered_all=%s",
        payload.bid_id,
        len(package.sections),
        package.consistency_checks.get("rendered_all_sections"),
    )
    return package
