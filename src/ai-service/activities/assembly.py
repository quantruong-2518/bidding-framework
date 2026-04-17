"""S8 Assembly activity (Phase 2.1 stub)."""

from __future__ import annotations

import logging

from temporalio import activity

from workflows.artifacts import AssemblyInput, ProposalPackage, ProposalSection

logger = logging.getLogger(__name__)


def _executive_section(input_: AssemblyInput) -> ProposalSection:
    body = (
        f"# Executive Summary\n\n"
        f"{input_.ba_draft.executive_summary}\n\n"
        f"- Total effort: {input_.wbs.total_effort_md:.1f} MD "
        f"over ~{input_.wbs.timeline_weeks} weeks.\n"
        f"- Proposed price: {input_.pricing.total:.2f} {input_.pricing.currency}.\n"
        f"- Architecture backbone: "
        f"{', '.join(ts.choice for ts in input_.sa_draft.tech_stack)}.\n"
    )
    return ProposalSection(
        heading="Executive Summary",
        body_markdown=body,
        sourced_from=["ba_draft", "wbs", "pricing", "sa_draft"],
    )


def _solution_section(input_: AssemblyInput) -> ProposalSection:
    bullets = "\n".join(
        f"- **{component.name}** — {component.responsibility}"
        for component in input_.hld.components
    )
    body = f"# Proposed Solution\n\n{input_.hld.architecture_overview}\n\n{bullets}\n"
    return ProposalSection(
        heading="Proposed Solution",
        body_markdown=body,
        sourced_from=["hld", "sa_draft"],
    )


def _delivery_section(input_: AssemblyInput) -> ProposalSection:
    phases = "\n".join(
        f"- {it.id} · {it.name} · {it.effort_md:.1f} MD" for it in input_.wbs.items
    )
    body = f"# Delivery Plan\n\n{phases}\n\nCritical path: {', '.join(input_.wbs.critical_path)}"
    return ProposalSection(
        heading="Delivery Plan",
        body_markdown=body,
        sourced_from=["wbs"],
    )


def _compliance_section(input_: AssemblyInput) -> ProposalSection:
    items = "\n".join(
        f"- **{c.framework}** — {c.requirement}" for c in input_.domain_notes.compliance
    )
    body = f"# Compliance + Domain Considerations\n\n{items}\n"
    return ProposalSection(
        heading="Compliance + Domain",
        body_markdown=body,
        sourced_from=["domain_notes"],
    )


def _commercial_section(input_: AssemblyInput) -> ProposalSection:
    lines = "\n".join(f"- {pl.label}: {pl.amount:.2f} {pl.unit}" for pl in input_.pricing.lines)
    body = (
        f"# Commercial Proposal\n\n"
        f"Model: {input_.pricing.model}. Currency: {input_.pricing.currency}.\n\n"
        f"{lines}\n\n"
        f"**Total: {input_.pricing.total:.2f} {input_.pricing.currency}** "
        f"(margin {input_.pricing.margin_pct:.1f}%)."
    )
    return ProposalSection(
        heading="Commercial",
        body_markdown=body,
        sourced_from=["pricing"],
    )


@activity.defn(name="assembly_activity")
async def assembly_activity(payload: AssemblyInput) -> ProposalPackage:
    """Compile all draft artifacts into a proposal skeleton."""
    activity.logger.info("assembly.start bid_id=%s", payload.bid_id)

    sections = [
        _executive_section(payload),
        _solution_section(payload),
        _delivery_section(payload),
        _compliance_section(payload),
        _commercial_section(payload),
    ]

    consistency = {
        "has_executive_summary": True,
        "has_solution_section": True,
        "has_delivery_plan": bool(payload.wbs.items),
        "has_commercial_section": bool(payload.pricing.lines),
        "compliance_covered": bool(payload.domain_notes.compliance),
    }

    package = ProposalPackage(
        bid_id=payload.bid_id,
        title=payload.title,
        sections=sections,
        appendices=["Assumptions (BA)", "Risk register (BA + SA)"],
        consistency_checks=consistency,
    )
    activity.logger.info(
        "assembly.done bid_id=%s sections=%d", payload.bid_id, len(sections)
    )
    return package
