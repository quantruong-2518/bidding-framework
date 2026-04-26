"""Pydantic DTOs for bid workflow states and activity I/O."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from workflows.base import (  # re-exported below for backwards compatibility
    BidProfile,
    RequirementAtom,
    RequirementCategory,
    TriageRecommendation,
    WorkflowState,
    utcnow,
)
from typing import Literal


class IntakeInput(BaseModel):
    """Raw RFP metadata handed to S0."""

    client_name: str
    rfp_text: str
    deadline: datetime
    region: str
    industry: str


class BidCard(BaseModel):
    """S0 output — structured bid opportunity header."""

    bid_id: UUID = Field(default_factory=uuid4)
    client_name: str
    industry: str
    region: str
    deadline: datetime
    scope_summary: str
    technology_keywords: list[str] = Field(default_factory=list)
    estimated_profile: BidProfile
    requirements_raw: list[str] = Field(default_factory=list)
    # Phase 3.4-A multi-tenant override; when None the workflow falls back to
    # slugify(client_name). Set explicitly to disambiguate clients that share a name.
    tenant_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TriageDecision(BaseModel):
    """S1 output — multi-criteria score + recommendation."""

    score_breakdown: dict[str, float]
    overall_score: float = Field(ge=0.0, le=100.0)
    recommendation: TriageRecommendation
    rationale: str


class HumanTriageSignal(BaseModel):
    """Payload delivered to the S1 human-gate signal handler."""

    approved: bool
    reviewer: str
    notes: str | None = None
    bid_profile_override: BidProfile | None = None


class ScopingResult(BaseModel):
    """S2 output — decomposition, stream routing, and team sizing hint."""

    requirement_map: list[RequirementAtom] = Field(default_factory=list)
    stream_assignments: dict[str, list[str]] = Field(default_factory=dict)
    team_suggestion: dict[str, int] = Field(default_factory=dict)


# Artifact types are imported HERE, after the types they depend on are defined,
# but BEFORE BidState so its annotations resolve without needing model_rebuild.
# The import order is load-bearing — do not move it.
from workflows.artifacts import (  # noqa: E402
    BusinessRequirementsDraft,
    ConvergenceReport,
    DomainNotes,
    HLDDraft,
    PricingDraft,
    ProposalPackage,
    RetrospectiveDraft,
    ReviewComment,
    ReviewRecord,
    ReviewVerdict,
    ReviewerRole,
    SolutionArchitectureDraft,
    SubmissionRecord,
    WBSDraft,
)


class HumanReviewSignal(BaseModel):
    """Payload delivered to the S9 human-review signal handler.

    Sent by a reviewer through NestJS `POST /bids/:id/workflow/review-signal`.
    `comments` populate the review record and drive the loop-back target.
    """

    verdict: ReviewVerdict
    reviewer: str
    reviewer_role: ReviewerRole
    comments: list[ReviewComment] = Field(default_factory=list)
    notes: str | None = None


class LoopBack(BaseModel):
    """Audit record of one loop-back event during S9 review rounds."""

    round: int
    target_state: Literal["S2", "S5", "S6", "S8"]
    reason: str
    at: datetime


class BidState(BaseModel):
    """Snapshot returned by workflow queries and on completion.

    Phase 2.1 extends this with artifact fields for S3..S11. All new fields are
    Optional (or empty list) so S0/S1/S2 queries remain backwards-compatible.
    """

    bid_id: UUID
    current_state: WorkflowState
    bid_card: BidCard | None = None
    triage: TriageDecision | None = None
    scoping: ScopingResult | None = None
    profile: BidProfile | None = None
    ba_draft: BusinessRequirementsDraft | None = None
    sa_draft: SolutionArchitectureDraft | None = None
    domain_notes: DomainNotes | None = None
    convergence: ConvergenceReport | None = None
    hld: HLDDraft | None = None
    wbs: WBSDraft | None = None
    pricing: PricingDraft | None = None
    proposal_package: ProposalPackage | None = None
    reviews: list[ReviewRecord] = Field(default_factory=list)
    submission: SubmissionRecord | None = None
    retrospective: RetrospectiveDraft | None = None
    loop_back_history: list[LoopBack] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BidWorkflowInput(BaseModel):
    """Top-level workflow arg. Exactly one of `intake` or `prebuilt_card` must be set.

    `intake` triggers S0 (parse RFP text into a BidCard).
    `prebuilt_card` skips S0 when upstream already has structured fields.
    """

    intake: IntakeInput | None = None
    prebuilt_card: BidCard | None = None


class StartWorkflowResponse(BaseModel):
    """Return shape of POST /workflows/bid/start."""

    workflow_id: str
    run_id: str
    task_queue: str


__all__ = [
    "BidProfile",
    "WorkflowState",
    "RequirementCategory",
    "RequirementAtom",
    "TriageRecommendation",
    "IntakeInput",
    "BidCard",
    "TriageDecision",
    "HumanTriageSignal",
    "HumanReviewSignal",
    "LoopBack",
    "ScopingResult",
    "BidState",
    "BidWorkflowInput",
    "StartWorkflowResponse",
]
