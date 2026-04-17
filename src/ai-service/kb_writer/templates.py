"""Render Pydantic artifact DTOs into markdown with `kind: bid_output` frontmatter.

Plain f-string + `textwrap.dedent` — no Jinja dep. Each render function takes the
artifact (and bid_id + phase where the artifact doesn't carry them) and returns
a full markdown string ready to write to disk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from textwrap import dedent
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


# --- S0 Bid Card ------------------------------------------------------------


def render_bid_card(card: BidCard) -> str:
    body = dedent(
        f"""\
        **Client:** {card.client_name}
        **Industry:** {card.industry}
        **Region:** {card.region}
        **Deadline:** {card.deadline.isoformat()}
        **Estimated profile:** {card.estimated_profile}

        ## Scope summary

        {card.scope_summary or "_(empty)_"}

        ## Technology keywords

        {_bullets(card.technology_keywords)}

        ## Raw requirements

        {_bullets(card.requirements_raw)}
        """
    )
    return _wrap(body, bid_id=card.bid_id, phase="S0_DONE", artifact="bid_card", title=f"Bid Card — {card.client_name}")


# --- S1 Triage --------------------------------------------------------------


def render_triage(triage: TriageDecision, *, bid_id: UUID) -> str:
    score_rows = [[k, f"{v:.2f}"] for k, v in triage.score_breakdown.items()]
    body = dedent(
        f"""\
        **Recommendation:** {triage.recommendation}
        **Overall score:** {triage.overall_score:.2f}

        ## Rationale

        {triage.rationale}

        ## Score breakdown

        {_table(["Criterion", "Score"], score_rows)}
        """
    )
    return _wrap(body, bid_id=bid_id, phase="S1_DONE", artifact="triage", title="Triage Decision")


# --- S2 Scoping -------------------------------------------------------------


def render_scoping(scoping: ScopingResult, *, bid_id: UUID) -> str:
    atom_rows = [
        [atom.id, atom.category, atom.text.replace("\n", " ")[:200]]
        for atom in scoping.requirement_map
    ]
    stream_rows = [[stream, ", ".join(atoms)] for stream, atoms in scoping.stream_assignments.items()]
    team_rows = [[role, str(count)] for role, count in scoping.team_suggestion.items()]

    body = dedent(
        f"""\
        ## Requirement atoms ({len(scoping.requirement_map)})

        {_table(["ID", "Category", "Text"], atom_rows)}

        ## Stream assignments

        {_table(["Stream", "Atoms"], stream_rows) if stream_rows else "_(none)_"}

        ## Team suggestion

        {_table(["Role", "Count"], team_rows) if team_rows else "_(none)_"}
        """
    )
    return _wrap(body, bid_id=bid_id, phase="S2_DONE", artifact="scoping", title="Scoping Result")


# --- S3a Business Analysis -------------------------------------------------


def render_ba(draft: BusinessRequirementsDraft) -> str:
    def fr_row(fr: FunctionalRequirement) -> list[str]:
        return [fr.id, fr.priority, fr.title, fr.description.replace("\n", " ")[:200]]

    risk_rows = [[r.title, r.likelihood, r.impact, r.mitigation] for r in draft.risks]
    similar_rows = [[s.project_id, f"{s.relevance_score:.2f}", s.why_relevant] for s in draft.similar_projects]

    body = dedent(
        f"""\
        **Confidence:** {draft.confidence:.2f}

        ## Executive summary

        {draft.executive_summary or "_(empty)_"}

        ## Business objectives

        {_bullets(draft.business_objectives)}

        ## In scope

        {_bullets(draft.scope.get("in_scope", []))}

        ## Out of scope

        {_bullets(draft.scope.get("out_of_scope", []))}

        ## Functional requirements

        {_table(["ID", "Priority", "Title", "Description"], [fr_row(fr) for fr in draft.functional_requirements])}

        ## Assumptions

        {_bullets(draft.assumptions)}

        ## Constraints

        {_bullets(draft.constraints)}

        ## Success criteria

        {_bullets(draft.success_criteria)}

        ## Risks

        {_table(["Title", "Likelihood", "Impact", "Mitigation"], risk_rows)}

        ## Similar projects

        {_table(["Project ID", "Relevance", "Why relevant"], similar_rows)}

        ## Sources

        {_bullets(draft.sources)}
        """
    )
    return _wrap(body, bid_id=draft.bid_id, phase="S3_DONE", artifact="ba_draft", title="Business Requirements Draft")


# --- S3b Solution Architecture ---------------------------------------------


def render_sa(draft: SolutionArchitectureDraft) -> str:
    stack_rows = [[c.layer, c.choice, c.rationale] for c in draft.tech_stack]
    pattern_rows = [[p.name, p.description, ", ".join(p.applies_to)] for p in draft.architecture_patterns]
    nfr_rows = [[k, v] for k, v in draft.nfr_targets.items()]
    risk_rows = [[r.title, r.likelihood, r.impact, r.mitigation] for r in draft.technical_risks]

    body = dedent(
        f"""\
        **Confidence:** {draft.confidence:.2f}

        ## Tech stack

        {_table(["Layer", "Choice", "Rationale"], stack_rows)}

        ## Architecture patterns

        {_table(["Pattern", "Description", "Applies to"], pattern_rows)}

        ## NFR targets

        {_table(["Key", "Target"], nfr_rows)}

        ## Technical risks

        {_table(["Title", "Likelihood", "Impact", "Mitigation"], risk_rows)}

        ## Integrations

        {_bullets(draft.integrations)}

        ## Sources

        {_bullets(draft.sources)}
        """
    )
    return _wrap(body, bid_id=draft.bid_id, phase="S3_DONE", artifact="sa_draft", title="Solution Architecture Draft")


# --- S3c Domain Notes -------------------------------------------------------


def render_domain(notes: DomainNotes) -> str:
    compliance_rows = [
        [c.framework, c.requirement, "yes" if c.applies else "no", c.notes or ""]
        for c in notes.compliance
    ]
    practice_rows = [[p.title, p.description] for p in notes.best_practices]
    glossary_rows = [[term, definition] for term, definition in notes.glossary.items()]

    body = dedent(
        f"""\
        **Industry:** {notes.industry}
        **Confidence:** {notes.confidence:.2f}

        ## Compliance

        {_table(["Framework", "Requirement", "Applies", "Notes"], compliance_rows)}

        ## Best practices

        {_table(["Title", "Description"], practice_rows)}

        ## Industry constraints

        {_bullets(notes.industry_constraints)}

        ## Glossary

        {_table(["Term", "Definition"], glossary_rows)}

        ## Sources

        {_bullets(notes.sources)}
        """
    )
    return _wrap(body, bid_id=notes.bid_id, phase="S3_DONE", artifact="domain_notes", title="Domain Notes")


# --- S4 Convergence ---------------------------------------------------------


def render_convergence(report: ConvergenceReport) -> str:
    def conflict_section(c: StreamConflict) -> str:
        return dedent(
            f"""\
            ### {c.topic} ({c.severity})

            - **Streams:** {", ".join(c.streams)}
            - **Description:** {c.description}
            - **Proposed resolution:** {c.proposed_resolution}
            """
        ).rstrip()

    readiness_rows = [[k, f"{v:.2f}"] for k, v in report.readiness.items()]
    conflicts_md = "\n\n".join(conflict_section(c) for c in report.conflicts) if report.conflicts else "_(no conflicts detected)_"

    body = dedent(
        f"""\
        ## Unified summary

        {report.unified_summary}

        ## Readiness

        {_table(["Stream", "Score"], readiness_rows)}

        ## Conflicts ({len(report.conflicts)})

        {conflicts_md}

        ## Open questions

        {_bullets(report.open_questions)}
        """
    )
    return _wrap(body, bid_id=report.bid_id, phase="S4_DONE", artifact="convergence", title="Convergence Report")


# --- S5 HLD -----------------------------------------------------------------


def render_hld(hld: HLDDraft) -> str:
    comp_rows = [[c.name, c.responsibility, ", ".join(c.depends_on)] for c in hld.components]
    body = dedent(
        f"""\
        ## Architecture overview

        {hld.architecture_overview or "_(empty)_"}

        ## Components

        {_table(["Name", "Responsibility", "Depends on"], comp_rows)}

        ## Data flows

        {_bullets(hld.data_flows)}

        ## Integration points

        {_bullets(hld.integration_points)}

        ## Security approach

        {hld.security_approach or "_(empty)_"}

        ## Deployment model

        {hld.deployment_model or "_(empty)_"}
        """
    )
    return _wrap(body, bid_id=hld.bid_id, phase="S5_DONE", artifact="hld", title="High-Level Design")


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
    body = dedent(
        f"""\
        **Total effort:** {wbs.total_effort_md:.1f} MD
        **Timeline:** {wbs.timeline_weeks} weeks
        **Critical path:** {", ".join(wbs.critical_path) if wbs.critical_path else "_(none)_"}

        ## Work breakdown

        {_table(["ID", "Name", "Parent", "Effort (MD)", "Owner", "Depends on"], rows)}
        """
    )
    return _wrap(body, bid_id=wbs.bid_id, phase="S6_DONE", artifact="wbs", title="Work Breakdown Structure")


# --- S7 Pricing -------------------------------------------------------------


def render_pricing(pricing: PricingDraft) -> str:
    line_rows = [
        [line.label, f"{line.amount:.2f}", line.unit, line.notes or ""]
        for line in pricing.lines
    ]
    scenario_rows = [[name, f"{total:.2f}"] for name, total in pricing.scenarios.items()]
    body = dedent(
        f"""\
        **Model:** {pricing.model}
        **Currency:** {pricing.currency}
        **Subtotal:** {pricing.subtotal:.2f}
        **Margin:** {pricing.margin_pct:.1f}%
        **Total:** {pricing.total:.2f}

        ## Line items

        {_table(["Label", "Amount", "Unit", "Notes"], line_rows)}

        ## Scenarios

        {_table(["Scenario", "Total"], scenario_rows) if scenario_rows else "_(none)_"}

        ## Notes

        {pricing.notes or "_(empty)_"}
        """
    )
    return _wrap(body, bid_id=pricing.bid_id, phase="S7_DONE", artifact="pricing", title="Pricing Draft")


# --- S8 Proposal ------------------------------------------------------------


def render_proposal(pkg: ProposalPackage) -> str:
    section_bodies: list[str] = []
    for section in pkg.sections:
        sources = f" _(sourced from: {', '.join(section.sourced_from)})_" if section.sourced_from else ""
        section_bodies.append(f"## {section.heading}{sources}\n\n{section.body_markdown.strip()}")
    body_md = "\n\n".join(section_bodies) if section_bodies else "_(no sections)_"
    check_rows = [[k, "✅" if v else "❌"] for k, v in pkg.consistency_checks.items()]
    body = dedent(
        f"""\
        **Title:** {pkg.title}

        ## Sections ({len(pkg.sections)})

        {body_md}

        ## Appendices

        {_bullets(pkg.appendices)}

        ## Consistency checks

        {_table(["Check", "Pass"], check_rows) if check_rows else "_(none)_"}
        """
    )
    return _wrap(body, bid_id=pkg.bid_id, phase="S8_DONE", artifact="proposal_package", title=pkg.title)


# --- S9 Review --------------------------------------------------------------


def render_review(record: ReviewRecord, *, round_index: int) -> str:
    comment_rows = [
        [c.section, c.severity, c.message, c.target_state or ""]
        for c in record.comments
    ]
    body = dedent(
        f"""\
        **Reviewer:** {record.reviewer} ({record.reviewer_role})
        **Verdict:** {record.verdict}
        **Reviewed at:** {record.reviewed_at.isoformat()}
        **Round:** {round_index}

        ## Comments

        {_table(["Section", "Severity", "Message", "Target state"], comment_rows) if comment_rows else "_(no comments)_"}
        """
    )
    return _wrap(body, bid_id=record.bid_id, phase="S9_DONE", artifact="review", title=f"Review round {round_index} — {record.reviewer}")


# --- S10 Submission ---------------------------------------------------------


def render_submission(sub: SubmissionRecord) -> str:
    check_rows = [[k, "✅" if v else "❌"] for k, v in sub.checklist.items()]
    body = dedent(
        f"""\
        **Submitted at:** {sub.submitted_at.isoformat()}
        **Channel:** {sub.channel}
        **Confirmation ID:** {sub.confirmation_id or "_(pending)_"}
        **Package checksum:** {sub.package_checksum or "_(none)_"}

        ## Checklist

        {_table(["Item", "Pass"], check_rows) if check_rows else "_(empty)_"}
        """
    )
    return _wrap(body, bid_id=sub.bid_id, phase="S10_DONE", artifact="submission", title="Submission Record")


# --- S11 Retrospective ------------------------------------------------------


def render_retrospective(retro: RetrospectiveDraft) -> str:
    lesson_rows = [[l.title, l.category, l.detail] for l in retro.lessons]
    body = dedent(
        f"""\
        **Outcome:** {retro.outcome}

        ## Lessons ({len(retro.lessons)})

        {_table(["Title", "Category", "Detail"], lesson_rows)}

        ## KB updates queued

        {_bullets(retro.kb_updates)}
        """
    )
    return _wrap(body, bid_id=retro.bid_id, phase="S11_DONE", artifact="retrospective", title="Retrospective")


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

    body = dedent(
        f"""\
        **Client:** {title_client}
        **Profile:** {profile}
        **Deadline:** {deadline}
        **Current state:** {state.current_state}

        ## Artifacts

        {chr(10).join(links) if links else "_(none yet)_"}
        """
    )
    return _wrap(body, bid_id=state.bid_id, phase=state.current_state, artifact="index", title=f"Bid workspace — {title_client}")


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
]
