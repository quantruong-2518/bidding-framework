"""Pydantic DTOs for S3b..S11 artifacts.

Kept separate from `workflows/models.py` to avoid that file ballooning past the
S0-S2 core contract. S3a's BA draft lives in `agents/models.py` because it's
directly produced by the BA LangGraph agent; for Phase 2.1 it's echoed by a
deterministic stub matching the same shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from agents.models import BusinessRequirementsDraft  # re-export so downstream only imports from artifacts
from workflows.base import RequirementAtom

ReviewVerdict = Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED"]
ReviewerRole = Literal["bid_manager", "ba", "sa", "qc", "domain_expert", "solution_lead"]
SubmissionChannel = Literal["portal", "email", "in_person"]


# --- S3a Business Analysis ---------------------------------------------------
# `BusinessRequirementsDraft` lives in agents/models.py; re-exported above so the
# workflow + NestJS artifact endpoint can pull everything from one module.


# --- S3b Solution Architecture -----------------------------------------------


class TechStackChoice(BaseModel):
    """One (layer → chosen technology) decision with a short rationale."""

    layer: str
    choice: str
    rationale: str


class ArchitecturePattern(BaseModel):
    name: str
    description: str
    applies_to: list[str] = Field(default_factory=list)


class TechnicalRisk(BaseModel):
    title: str
    likelihood: str
    impact: str
    mitigation: str


class SolutionArchitectureDraft(BaseModel):
    """S3b output — tech stack + architecture patterns + technical risks."""

    bid_id: UUID
    tech_stack: list[TechStackChoice] = Field(default_factory=list)
    architecture_patterns: list[ArchitecturePattern] = Field(default_factory=list)
    nfr_targets: dict[str, str] = Field(default_factory=dict)
    technical_risks: list[TechnicalRisk] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    sources: list[str] = Field(default_factory=list)


# --- S3c Domain Mining -------------------------------------------------------


class ComplianceItem(BaseModel):
    framework: str
    requirement: str
    applies: bool = True
    notes: str | None = None


class DomainPractice(BaseModel):
    title: str
    description: str


class DomainNotes(BaseModel):
    """S3c output — compliance checklist + best practices + industry constraints."""

    bid_id: UUID
    industry: str
    compliance: list[ComplianceItem] = Field(default_factory=list)
    best_practices: list[DomainPractice] = Field(default_factory=list)
    industry_constraints: list[str] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    sources: list[str] = Field(default_factory=list)


# --- S4 Convergence ----------------------------------------------------------


class StreamConflict(BaseModel):
    """A point where two streams disagreed — Phase 2.1 stub: detected = False."""

    streams: list[str]
    topic: str
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    proposed_resolution: str


class ConvergenceReport(BaseModel):
    """S4 output — merged stream view + conflicts + readiness score."""

    bid_id: UUID
    unified_summary: str
    readiness: dict[str, float] = Field(default_factory=dict)  # stream_id -> 0..1
    conflicts: list[StreamConflict] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


# --- S5 Solution Design (HLD) ------------------------------------------------


class HLDComponent(BaseModel):
    name: str
    responsibility: str
    depends_on: list[str] = Field(default_factory=list)


class HLDDraft(BaseModel):
    """S5 output — high-level design."""

    bid_id: UUID
    architecture_overview: str
    components: list[HLDComponent] = Field(default_factory=list)
    data_flows: list[str] = Field(default_factory=list)
    integration_points: list[str] = Field(default_factory=list)
    security_approach: str = ""
    deployment_model: str = ""
    # Phase 2-real: cost + tier of the LLM run that produced this draft.
    # None when the stub fallback path produced it.
    llm_cost_usd: float | None = None
    llm_tier_used: str | None = None


# --- S6 WBS + Estimation -----------------------------------------------------


class WBSItem(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    effort_md: float = 0.0  # man-days
    owner_role: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class WBSDraft(BaseModel):
    """S6 output — work breakdown + effort totals + timeline hint."""

    bid_id: UUID
    items: list[WBSItem] = Field(default_factory=list)
    total_effort_md: float = 0.0
    timeline_weeks: int = 0
    critical_path: list[str] = Field(default_factory=list)
    llm_cost_usd: float | None = None
    llm_tier_used: str | None = None


# --- S7 Commercial Strategy --------------------------------------------------


class PricingLine(BaseModel):
    label: str
    amount: float
    unit: str = "USD"
    notes: str | None = None


class PricingDraft(BaseModel):
    """S7 output — pricing model (advisory — humans approve)."""

    bid_id: UUID
    model: Literal["fixed_price", "time_and_materials", "hybrid"] = "fixed_price"
    currency: str = "USD"
    lines: list[PricingLine] = Field(default_factory=list)
    subtotal: float = 0.0
    margin_pct: float = 0.0
    total: float = 0.0
    scenarios: dict[str, float] = Field(default_factory=dict)
    notes: str = ""
    llm_cost_usd: float | None = None
    llm_tier_used: str | None = None


# --- S8 Assembly -------------------------------------------------------------


class ProposalSection(BaseModel):
    heading: str
    body_markdown: str
    sourced_from: list[str] = Field(default_factory=list)  # artifact names


class ProposalPackage(BaseModel):
    """S8 output — compiled proposal sections ready for review."""

    bid_id: UUID
    title: str
    sections: list[ProposalSection] = Field(default_factory=list)
    appendices: list[str] = Field(default_factory=list)
    consistency_checks: dict[str, bool] = Field(default_factory=dict)


# --- S9 Review Gate ----------------------------------------------------------


class ReviewComment(BaseModel):
    section: str
    severity: Literal["NIT", "MINOR", "MAJOR", "BLOCKER"]
    message: str
    target_state: Literal["S2", "S5", "S6", "S8"] | None = None


class ReviewRecord(BaseModel):
    """S9 output — one review round (there may be multiple in Phase 2.4)."""

    bid_id: UUID
    reviewer_role: ReviewerRole
    reviewer: str
    verdict: ReviewVerdict
    comments: list[ReviewComment] = Field(default_factory=list)
    reviewed_at: datetime


# --- S10 Submission ----------------------------------------------------------


class SubmissionRecord(BaseModel):
    """S10 output — artefact snapshot + delivery metadata."""

    bid_id: UUID
    submitted_at: datetime
    channel: SubmissionChannel = "portal"
    confirmation_id: str | None = None
    package_checksum: str | None = None
    checklist: dict[str, bool] = Field(default_factory=dict)


# --- S11 Retrospective -------------------------------------------------------


class Lesson(BaseModel):
    title: str
    category: Literal["win_pattern", "loss_pattern", "estimation", "process"] = "process"
    detail: str


class KBDelta(BaseModel):
    """Conv 15 — a single KB update suggestion the retrospective produced.

    All AI-generated deltas land in the vault with ``ai_generated: true`` in
    frontmatter so a downstream reviewer can approve / reject before the next
    ingestion run promotes them into the real KB. ``approved=True`` is set by
    a human-in-loop step (not yet wired — Conv 16+).
    """

    id: str
    type: Literal["new_lesson", "update_similar_project", "deprecate_note"] = "new_lesson"
    # Wrapper-managed: the retrospective agent's _normalise_kb_deltas always
    # rewrites this to lessons/<bid_id>-<delta_id>.md so the LLM doesn't need
    # to know the vault layout. Default empty so structured parsing accepts
    # the LLM payload without target_path.
    target_path: str = ""
    title: str
    content_markdown: str
    rationale: str = ""
    ai_generated: bool = True
    approved: bool = False


class RetrospectiveDraft(BaseModel):
    """S11 output — lessons + KB feedback queue."""

    bid_id: UUID
    outcome: Literal["WIN", "LOSS", "PENDING"] = "PENDING"
    lessons: list[Lesson] = Field(default_factory=list)
    # Conv 15: legacy `kb_updates` (list of paths/titles) preserved for
    # backwards compat; new `kb_deltas` carries the structured per-suggestion
    # payload the LLM produces and the Obsidian write-back persists.
    kb_updates: list[str] = Field(default_factory=list)
    kb_deltas: list[KBDelta] = Field(default_factory=list)
    # Conv 15: optional cost roll-up — None when stub fallback ran.
    llm_cost_usd: float | None = None
    llm_tier_used: str | None = None


# --- Activity input shapes ---------------------------------------------------


class StreamInput(BaseModel):
    """Shared shape handed to each S3 stream activity."""

    bid_id: UUID
    client_name: str
    industry: str
    region: str
    # Phase 3.4-A: required so KB retrieval enforces multi-tenant isolation.
    # Workflow derives this from BidCard.tenant_id (override) or slugify(client_name).
    tenant_id: str
    requirements: list[RequirementAtom] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deadline: datetime


class ConvergenceInput(BaseModel):
    bid_id: UUID
    ba_draft: BusinessRequirementsDraft
    sa_draft: SolutionArchitectureDraft
    domain_notes: DomainNotes


class SolutionDesignInput(BaseModel):
    bid_id: UUID
    convergence: ConvergenceReport
    sa_draft: SolutionArchitectureDraft


class WBSInput(BaseModel):
    bid_id: UUID
    hld: HLDDraft | None = None
    ba_draft: BusinessRequirementsDraft


class CommercialInput(BaseModel):
    bid_id: UUID
    wbs: WBSDraft
    industry: str


class AssemblyInput(BaseModel):
    """S8 activity input.

    Phase 3.1 widened the payload so Jinja templates get the full bid context
    (client_name on cover, triage rationale in exec summary, scoping in BR,
    etc.). Every new field is optional so the stub-fallback path keeps working
    on old callers.
    """

    bid_id: UUID
    title: str
    ba_draft: BusinessRequirementsDraft
    sa_draft: SolutionArchitectureDraft
    domain_notes: DomainNotes
    hld: HLDDraft | None = None
    wbs: WBSDraft
    pricing: PricingDraft | None = None
    # Phase 3.1 additions — feed richer Jinja context without changing any
    # downstream DTOs. `generated_at` is set by the workflow via `workflow.now()`
    # to stay Temporal-deterministic. `bid_card` / `triage` / `scoping` are
    # typed `Any` to avoid the `workflows.models` → `artifacts.py` import cycle
    # (they're consumed only by Jinja templates which introspect at runtime).
    bid_card: Any = None
    triage: Any = None
    scoping: Any = None
    convergence: ConvergenceReport | None = None
    reviews: list[ReviewRecord] = Field(default_factory=list)
    generated_at: datetime | None = None


class ReviewInput(BaseModel):
    bid_id: UUID
    package: ProposalPackage


class SubmissionInput(BaseModel):
    bid_id: UUID
    package: ProposalPackage
    reviews: list[ReviewRecord] = Field(default_factory=list)


class RetrospectiveInput(BaseModel):
    """Conv 15 widened — optional earlier-phase artifacts so the LLM has
    context to reflect on. Stub path uses only ``submission`` (backwards
    compatible); real-LLM path consumes whichever optional fields are set.
    Field types use forward refs to dodge the workflows.models import cycle.
    """

    bid_id: UUID
    submission: SubmissionRecord
    ba_draft: BusinessRequirementsDraft | None = None
    sa_draft: SolutionArchitectureDraft | None = None
    domain_notes: DomainNotes | None = None
    convergence: ConvergenceReport | None = None
    wbs: WBSDraft | None = None
    pricing: PricingDraft | None = None
    reviews: list[ReviewRecord] = Field(default_factory=list)
    client_name: str | None = None
    industry: str | None = None


__all__ = [
    "BusinessRequirementsDraft",
    "SolutionArchitectureDraft",
    "TechStackChoice",
    "ArchitecturePattern",
    "TechnicalRisk",
    "DomainNotes",
    "ComplianceItem",
    "DomainPractice",
    "ConvergenceReport",
    "StreamConflict",
    "HLDDraft",
    "HLDComponent",
    "WBSDraft",
    "WBSItem",
    "PricingDraft",
    "PricingLine",
    "ProposalPackage",
    "ProposalSection",
    "ReviewRecord",
    "ReviewComment",
    "ReviewVerdict",
    "ReviewerRole",
    "SubmissionRecord",
    "SubmissionChannel",
    "RetrospectiveDraft",
    "Lesson",
    "KBDelta",
    "StreamInput",
    "ConvergenceInput",
    "SolutionDesignInput",
    "WBSInput",
    "CommercialInput",
    "AssemblyInput",
    "ReviewInput",
    "SubmissionInput",
    "RetrospectiveInput",
]
