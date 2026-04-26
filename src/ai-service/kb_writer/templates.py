"""Render Pydantic artifact DTOs into markdown with `kind: bid_output` frontmatter.

Each render function composes a list of markdown lines, joins them with `\\n`,
then wraps the result with standard frontmatter via `_wrap`. No `textwrap.dedent`
— interpolated multi-line values would break the common-prefix strip and
leading whitespace would be interpreted as a code block by Markdown renderers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import frontmatter

from agents.models import BusinessRequirementsDraft, FunctionalRequirement
from workflows.artifacts import (
    ConvergenceReport,
    DomainNotes,
    HLDDraft,
    PricingDraft,
    ProposalPackage,
    RetrospectiveDraft,
    ReviewRecord,
    SolutionArchitectureDraft,
    StreamConflict,
    SubmissionRecord,
    WBSDraft,
)
from workflows.models import BidCard, BidState, ScopingResult, TriageDecision


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wrap(body: str, *, bid_id: UUID, phase: str, artifact: str, title: str) -> str:
    """Attach standard frontmatter + H1 title to a rendered artifact body."""
    post = frontmatter.Post(
        content=f"# {title}\n\n{body.rstrip()}\n",
        kind="bid_output",
        bid_id=str(bid_id),
        phase=phase,
        artifact=artifact,
        generated_at=_now_iso(),
    )
    return frontmatter.dumps(post) + "\n"


def _bullets(items: Iterable[str]) -> str:
    rendered = [f"- {item}" for item in items if str(item).strip()]
    return "\n".join(rendered) if rendered else "- _(none)_"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_(no rows)_"
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = "\n".join("| " + " | ".join(cell for cell in row) + " |" for row in rows)
    return "\n".join([head, sep, body])


def _section(heading: str, body: str) -> list[str]:
    return [f"## {heading}", "", body, ""]


def _join(parts: list[str]) -> str:
    return "\n".join(parts)


# --- S0 Bid Card ------------------------------------------------------------


def render_bid_card(card: BidCard) -> str:
    parts: list[str] = [
        f"**Client:** {card.client_name}",
        f"**Industry:** {card.industry}",
        f"**Region:** {card.region}",
        f"**Deadline:** {card.deadline.isoformat()}",
        f"**Estimated profile:** {card.estimated_profile}",
        "",
        *_section("Scope summary", card.scope_summary or "_(empty)_"),
        *_section("Technology keywords", _bullets(card.technology_keywords)),
        *_section("Raw requirements", _bullets(card.requirements_raw)),
    ]
    return _wrap(_join(parts), bid_id=card.bid_id, phase="S0_DONE", artifact="bid_card", title=f"Bid Card — {card.client_name}")


# --- S1 Triage --------------------------------------------------------------


def render_triage(triage: TriageDecision, *, bid_id: UUID) -> str:
    score_rows = [[k, f"{v:.2f}"] for k, v in triage.score_breakdown.items()]
    parts: list[str] = [
        f"**Recommendation:** {triage.recommendation}",
        f"**Overall score:** {triage.overall_score:.2f}",
        "",
        *_section("Rationale", triage.rationale),
        *_section("Score breakdown", _table(["Criterion", "Score"], score_rows)),
    ]
    return _wrap(_join(parts), bid_id=bid_id, phase="S1_DONE", artifact="triage", title="Triage Decision")


# --- S2 Scoping -------------------------------------------------------------


def render_scoping(scoping: ScopingResult, *, bid_id: UUID) -> str:
    atom_rows = [
        [atom.id, atom.category, atom.text.replace("\n", " ")[:200]]
        for atom in scoping.requirement_map
    ]
    stream_rows = [[stream, ", ".join(atoms)] for stream, atoms in scoping.stream_assignments.items()]
    team_rows = [[role, str(count)] for role, count in scoping.team_suggestion.items()]

    parts: list[str] = [
        *_section(
            f"Requirement atoms ({len(scoping.requirement_map)})",
            _table(["ID", "Category", "Text"], atom_rows),
        ),
        *_section(
            "Stream assignments",
            _table(["Stream", "Atoms"], stream_rows) if stream_rows else "_(none)_",
        ),
        *_section(
            "Team suggestion",
            _table(["Role", "Count"], team_rows) if team_rows else "_(none)_",
        ),
    ]
    return _wrap(_join(parts), bid_id=bid_id, phase="S2_DONE", artifact="scoping", title="Scoping Result")


# --- S3a Business Analysis -------------------------------------------------


def render_ba(draft: BusinessRequirementsDraft) -> str:
    def fr_row(fr: FunctionalRequirement) -> list[str]:
        return [fr.id, fr.priority, fr.title, fr.description.replace("\n", " ")[:200]]

    risk_rows = [[r.title, r.likelihood, r.impact, r.mitigation] for r in draft.risks]
    similar_rows = [[s.project_id, f"{s.relevance_score:.2f}", s.why_relevant] for s in draft.similar_projects]

    parts: list[str] = [
        f"**Confidence:** {draft.confidence:.2f}",
        "",
        *_section("Executive summary", draft.executive_summary or "_(empty)_"),
        *_section("Business objectives", _bullets(draft.business_objectives)),
        *_section("In scope", _bullets(draft.scope.get("in_scope", []))),
        *_section("Out of scope", _bullets(draft.scope.get("out_of_scope", []))),
        *_section(
            "Functional requirements",
            _table(["ID", "Priority", "Title", "Description"], [fr_row(fr) for fr in draft.functional_requirements]),
        ),
        *_section("Assumptions", _bullets(draft.assumptions)),
        *_section("Constraints", _bullets(draft.constraints)),
        *_section("Success criteria", _bullets(draft.success_criteria)),
        *_section("Risks", _table(["Title", "Likelihood", "Impact", "Mitigation"], risk_rows)),
        *_section("Similar projects", _table(["Project ID", "Relevance", "Why relevant"], similar_rows)),
        *_section("Sources", _bullets(draft.sources)),
    ]
    return _wrap(_join(parts), bid_id=draft.bid_id, phase="S3_DONE", artifact="ba_draft", title="Business Requirements Draft")


# --- S3b Solution Architecture ---------------------------------------------


def render_sa(draft: SolutionArchitectureDraft) -> str:
    stack_rows = [[c.layer, c.choice, c.rationale] for c in draft.tech_stack]
    pattern_rows = [[p.name, p.description, ", ".join(p.applies_to)] for p in draft.architecture_patterns]
    nfr_rows = [[k, v] for k, v in draft.nfr_targets.items()]
    risk_rows = [[r.title, r.likelihood, r.impact, r.mitigation] for r in draft.technical_risks]

    parts: list[str] = [
        f"**Confidence:** {draft.confidence:.2f}",
        "",
        *_section("Tech stack", _table(["Layer", "Choice", "Rationale"], stack_rows)),
        *_section("Architecture patterns", _table(["Pattern", "Description", "Applies to"], pattern_rows)),
        *_section("NFR targets", _table(["Key", "Target"], nfr_rows)),
        *_section("Technical risks", _table(["Title", "Likelihood", "Impact", "Mitigation"], risk_rows)),
        *_section("Integrations", _bullets(draft.integrations)),
        *_section("Sources", _bullets(draft.sources)),
    ]
    return _wrap(_join(parts), bid_id=draft.bid_id, phase="S3_DONE", artifact="sa_draft", title="Solution Architecture Draft")


# --- S3c Domain Notes -------------------------------------------------------


def render_domain(notes: DomainNotes) -> str:
    compliance_rows = [
        [c.framework, c.requirement, "yes" if c.applies else "no", c.notes or ""]
        for c in notes.compliance
    ]
    practice_rows = [[p.title, p.description] for p in notes.best_practices]
    glossary_rows = [[term, definition] for term, definition in notes.glossary.items()]

    parts: list[str] = [
        f"**Industry:** {notes.industry}",
        f"**Confidence:** {notes.confidence:.2f}",
        "",
        *_section("Compliance", _table(["Framework", "Requirement", "Applies", "Notes"], compliance_rows)),
        *_section("Best practices", _table(["Title", "Description"], practice_rows)),
        *_section("Industry constraints", _bullets(notes.industry_constraints)),
        *_section("Glossary", _table(["Term", "Definition"], glossary_rows)),
        *_section("Sources", _bullets(notes.sources)),
    ]
    return _wrap(_join(parts), bid_id=notes.bid_id, phase="S3_DONE", artifact="domain_notes", title="Domain Notes")


# --- S4 Convergence ---------------------------------------------------------


def render_convergence(report: ConvergenceReport) -> str:
    def conflict_block(c: StreamConflict) -> str:
        return _join(
            [
                f"### {c.topic} ({c.severity})",
                "",
                f"- **Streams:** {', '.join(c.streams)}",
                f"- **Description:** {c.description}",
                f"- **Proposed resolution:** {c.proposed_resolution}",
            ]
        )

    readiness_rows = [[k, f"{v:.2f}"] for k, v in report.readiness.items()]
    conflicts_md = (
        "\n\n".join(conflict_block(c) for c in report.conflicts)
        if report.conflicts
        else "_(no conflicts detected)_"
    )

    parts: list[str] = [
        *_section("Unified summary", report.unified_summary),
        *_section("Readiness", _table(["Stream", "Score"], readiness_rows)),
        *_section(f"Conflicts ({len(report.conflicts)})", conflicts_md),
        *_section("Open questions", _bullets(report.open_questions)),
    ]
    return _wrap(_join(parts), bid_id=report.bid_id, phase="S4_DONE", artifact="convergence", title="Convergence Report")


# --- S5 HLD -----------------------------------------------------------------


def render_hld(hld: HLDDraft) -> str:
    comp_rows = [[c.name, c.responsibility, ", ".join(c.depends_on)] for c in hld.components]
    parts: list[str] = [
        *_section("Architecture overview", hld.architecture_overview or "_(empty)_"),
        *_section("Components", _table(["Name", "Responsibility", "Depends on"], comp_rows)),
        *_section("Data flows", _bullets(hld.data_flows)),
        *_section("Integration points", _bullets(hld.integration_points)),
        *_section("Security approach", hld.security_approach or "_(empty)_"),
        *_section("Deployment model", hld.deployment_model or "_(empty)_"),
    ]
    return _wrap(_join(parts), bid_id=hld.bid_id, phase="S5_DONE", artifact="hld", title="High-Level Design")


# --- S6 WBS -----------------------------------------------------------------


def render_wbs(wbs: WBSDraft) -> str:
    rows = [
        [
            item.id,
            item.name,
            item.parent_id or "",
            f"{item.effort_md:.1f}",
            item.owner_role or "",
            ", ".join(item.depends_on),
        ]
        for item in wbs.items
    ]
    parts: list[str] = [
        f"**Total effort:** {wbs.total_effort_md:.1f} MD",
        f"**Timeline:** {wbs.timeline_weeks} weeks",
        f"**Critical path:** {', '.join(wbs.critical_path) if wbs.critical_path else '_(none)_'}",
        "",
        *_section(
            "Work breakdown",
            _table(["ID", "Name", "Parent", "Effort (MD)", "Owner", "Depends on"], rows),
        ),
    ]
    return _wrap(_join(parts), bid_id=wbs.bid_id, phase="S6_DONE", artifact="wbs", title="Work Breakdown Structure")


# --- S7 Pricing -------------------------------------------------------------


def render_pricing(pricing: PricingDraft) -> str:
    line_rows = [
        [line.label, f"{line.amount:.2f}", line.unit, line.notes or ""]
        for line in pricing.lines
    ]
    scenario_rows = [[name, f"{total:.2f}"] for name, total in pricing.scenarios.items()]
    parts: list[str] = [
        f"**Model:** {pricing.model}",
        f"**Currency:** {pricing.currency}",
        f"**Subtotal:** {pricing.subtotal:.2f}",
        f"**Margin:** {pricing.margin_pct:.1f}%",
        f"**Total:** {pricing.total:.2f}",
        "",
        *_section("Line items", _table(["Label", "Amount", "Unit", "Notes"], line_rows)),
        *_section("Scenarios", _table(["Scenario", "Total"], scenario_rows) if scenario_rows else "_(none)_"),
        *_section("Notes", pricing.notes or "_(empty)_"),
    ]
    return _wrap(_join(parts), bid_id=pricing.bid_id, phase="S7_DONE", artifact="pricing", title="Pricing Draft")


# --- S8 Proposal ------------------------------------------------------------


def render_proposal(pkg: ProposalPackage) -> str:
    section_blocks: list[str] = []
    for section in pkg.sections:
        sources = f" _(sourced from: {', '.join(section.sourced_from)})_" if section.sourced_from else ""
        section_blocks.append(f"## {section.heading}{sources}\n\n{section.body_markdown.strip()}")
    sections_md = "\n\n".join(section_blocks) if section_blocks else "_(no sections)_"
    check_rows = [[k, "✅" if v else "❌"] for k, v in pkg.consistency_checks.items()]

    parts: list[str] = [
        f"**Title:** {pkg.title}",
        "",
        f"## Sections ({len(pkg.sections)})",
        "",
        sections_md,
        "",
        *_section("Appendices", _bullets(pkg.appendices)),
        *_section("Consistency checks", _table(["Check", "Pass"], check_rows) if check_rows else "_(none)_"),
    ]
    return _wrap(_join(parts), bid_id=pkg.bid_id, phase="S8_DONE", artifact="proposal_package", title=pkg.title)


# --- S9 Review --------------------------------------------------------------


def render_review(record: ReviewRecord, *, round_index: int) -> str:
    comment_rows = [
        [c.section, c.severity, c.message, c.target_state or ""]
        for c in record.comments
    ]
    parts: list[str] = [
        f"**Reviewer:** {record.reviewer} ({record.reviewer_role})",
        f"**Verdict:** {record.verdict}",
        f"**Reviewed at:** {record.reviewed_at.isoformat()}",
        f"**Round:** {round_index}",
        "",
        *_section(
            "Comments",
            _table(["Section", "Severity", "Message", "Target state"], comment_rows)
            if comment_rows
            else "_(no comments)_",
        ),
    ]
    return _wrap(_join(parts), bid_id=record.bid_id, phase="S9_DONE", artifact="review", title=f"Review round {round_index} — {record.reviewer}")


# --- S10 Submission ---------------------------------------------------------


def render_submission(sub: SubmissionRecord) -> str:
    check_rows = [[k, "✅" if v else "❌"] for k, v in sub.checklist.items()]
    parts: list[str] = [
        f"**Submitted at:** {sub.submitted_at.isoformat()}",
        f"**Channel:** {sub.channel}",
        f"**Confirmation ID:** {sub.confirmation_id or '_(pending)_'}",
        f"**Package checksum:** {sub.package_checksum or '_(none)_'}",
        "",
        *_section("Checklist", _table(["Item", "Pass"], check_rows) if check_rows else "_(empty)_"),
    ]
    return _wrap(_join(parts), bid_id=sub.bid_id, phase="S10_DONE", artifact="submission", title="Submission Record")


# --- S11 Retrospective ------------------------------------------------------


def render_retrospective(retro: RetrospectiveDraft) -> str:
    lesson_rows = [[l.title, l.category, l.detail] for l in retro.lessons]
    parts: list[str] = [
        f"**Outcome:** {retro.outcome}",
        "",
        *_section(
            f"Lessons ({len(retro.lessons)})",
            _table(["Title", "Category", "Detail"], lesson_rows),
        ),
        *_section("KB updates queued", _bullets(retro.kb_updates)),
    ]
    return _wrap(_join(parts), bid_id=retro.bid_id, phase="S11_DONE", artifact="retrospective", title="Retrospective")


# --- Index hub --------------------------------------------------------------


def render_index(state: BidState) -> str:
    bid = state.bid_card
    title_client = bid.client_name if bid else "unknown"
    profile = state.profile or (bid.estimated_profile if bid else "?")
    deadline = bid.deadline.isoformat() if bid else "?"

    def link(href: str, label: str) -> str:
        return f"- [[{href}|{label}]]"

    links: list[str] = []
    if bid:
        links.append(link("00-bid-card", "00 Bid Card"))
    if state.triage:
        links.append(link("01-triage", "01 Triage"))
    if state.scoping:
        links.append(link("02-scoping", "02 Scoping"))
    if state.ba_draft:
        links.append(link("03-ba", "03a BA Draft"))
    if state.sa_draft:
        links.append(link("03-sa", "03b SA Draft"))
    if state.domain_notes:
        links.append(link("03-domain", "03c Domain Notes"))
    if state.convergence:
        links.append(link("04-convergence", "04 Convergence"))
    if state.hld:
        links.append(link("05-hld", "05 HLD"))
    if state.wbs:
        links.append(link("06-wbs", "06 WBS"))
    if state.pricing:
        links.append(link("07-pricing", "07 Pricing"))
    if state.proposal_package:
        links.append(link("08-proposal", "08 Proposal"))
    for i, _ in enumerate(state.reviews, start=1):
        links.append(link(f"09-reviews/{i:02d}", f"09 Review round {i}"))
    if state.submission:
        links.append(link("10-submission", "10 Submission"))
    if state.retrospective:
        links.append(link("11-retrospective", "11 Retrospective"))

    parts: list[str] = [
        f"**Client:** {title_client}",
        f"**Profile:** {profile}",
        f"**Deadline:** {deadline}",
        f"**Current state:** {state.current_state}",
        "",
        "## Artifacts",
        "",
        "\n".join(links) if links else "_(none yet)_",
    ]
    return _wrap(_join(parts), bid_id=state.bid_id, phase=state.current_state, artifact="index", title=f"Bid workspace — {title_client}")


# ---------------------------------------------------------------------------
# Wave 2A — S0.5 atom + anchor + summary + compliance matrix renderers.
#
# Additive only: the workspace snapshot writer never imports these (the S0.5
# materialise activity does). Existing 15 render_* functions left untouched.
# ---------------------------------------------------------------------------


def render_atom_body(atom: "AtomFrontmatter", body_md: str) -> str:  # type: ignore[name-defined]
    """Re-export of :func:`kb_writer.atom_emitter.render_atom_body` so callers
    that already import :mod:`kb_writer.templates` for the legacy renderers
    don't need a second import."""
    from kb_writer.atom_emitter import render_atom_body as _impl

    return _impl(atom, body_md)


def render_anchor(anchor_md: str, *, bid_id: str, tenant_id: str) -> str:
    """Wrap a synth anchor body with frontmatter + H1 so the vault file is
    self-describing for ingestion."""
    body = (anchor_md or "").rstrip() + "\n"
    return _join(
        [
            "---",
            f"bid_id: {bid_id}",
            f"tenant_id: {tenant_id}",
            "kind: project_anchor",
            "role: derived",
            f"generated_at: {_now_iso()}",
            "---",
            "",
            body,
        ]
    )


def render_summary(summary_md: str, *, bid_id: str, tenant_id: str) -> str:
    """Wrap a synth summary body with frontmatter + H1."""
    body = (summary_md or "").rstrip() + "\n"
    return _join(
        [
            "---",
            f"bid_id: {bid_id}",
            f"tenant_id: {tenant_id}",
            "kind: project_summary",
            "role: derived",
            f"generated_at: {_now_iso()}",
            "---",
            "",
            body,
        ]
    )


def render_compliance_matrix(atoms: list["AtomFrontmatter"]) -> str:  # type: ignore[name-defined]
    """Render a compact compliance matrix from the active atoms.

    Filters to ``active=True`` + type ``compliance``; one row per atom with
    priority + category. Returns a markdown body (no frontmatter — caller
    wraps when writing to vault).
    """
    rows: list[list[str]] = []
    for atom in atoms or []:
        try:
            if not atom.active or atom.type != "compliance":
                continue
        except AttributeError:
            continue
        rows.append([atom.id, atom.priority, atom.category, atom.tenant_id])
    body_table = _table(["Atom ID", "Priority", "Category", "Tenant"], rows)
    return _join(
        [
            "# Compliance matrix",
            "",
            f"_{len(rows)} active compliance atom(s)._",
            "",
            body_table,
            "",
        ]
    )


__all__ = [
    "render_ba",
    "render_bid_card",
    "render_convergence",
    "render_domain",
    "render_hld",
    "render_index",
    "render_pricing",
    "render_proposal",
    "render_retrospective",
    "render_review",
    "render_sa",
    "render_scoping",
    "render_submission",
    "render_triage",
    "render_wbs",
    # Wave 2A additions:
    "render_atom_body",
    "render_anchor",
    "render_summary",
    "render_compliance_matrix",
]
