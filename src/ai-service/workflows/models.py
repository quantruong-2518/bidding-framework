"""Pydantic DTOs for bid workflow states and activity I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

BidProfile = Literal["S", "M", "L", "XL"]
"""Bid sizing used to pick a pipeline variant (see STATE_MACHINE.md)."""

WorkflowState = Literal[
    "S0",
    "S1",
    "S1_NO_BID",
    "S2",
    "S2_DONE",
    "S3",
    "S4",
    "S5",
    "S6",
    "S7",
    "S8",
    "S9",
    "S10",
    "S11",
]

RequirementCategory = Literal[
    "functional",
    "nfr",
    "technical",
    "compliance",
    "timeline",
    "unclear",
]

TriageRecommendation = Literal["BID", "NO_BID"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    created_at: datetime = Field(default_factory=_utcnow)


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


class RequirementAtom(BaseModel):
    """A single decomposed requirement with its category + trace source."""

    id: str
    text: str
    category: RequirementCategory
    source_section: str | None = None


class ScopingResult(BaseModel):
    """S2 output — decomposition, stream routing, and team sizing hint."""

    requirement_map: list[RequirementAtom] = Field(default_factory=list)
    stream_assignments: dict[str, list[str]] = Field(default_factory=dict)
    team_suggestion: dict[str, int] = Field(default_factory=dict)


class BidState(BaseModel):
    """Snapshot returned by workflow queries and on completion."""

    bid_id: UUID
    current_state: WorkflowState
    bid_card: BidCard | None = None
    triage: TriageDecision | None = None
    scoping: ScopingResult | None = None
    profile: BidProfile | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


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
