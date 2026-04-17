"""Pydantic DTOs for the S3 LangGraph agents (BA / SA / Domain)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Priority = Literal["MUST", "SHOULD", "COULD", "WONT"]


class FunctionalRequirement(BaseModel):
    """Single functional requirement line item synthesised by the BA agent."""

    id: str
    title: str
    description: str
    priority: Priority
    rationale: str


class RiskItem(BaseModel):
    """Qualitative risk entry — likelihood/impact are free-form LOW/MEDIUM/HIGH."""

    title: str
    likelihood: str
    impact: str
    mitigation: str


class SimilarProject(BaseModel):
    """Pointer to a KB project surfaced by RAG during BA analysis."""

    project_id: str
    relevance_score: float
    why_relevant: str


class BusinessRequirementsDraft(BaseModel):
    """Final structured output produced by the BA agent for downstream streams."""

    bid_id: UUID
    executive_summary: str
    business_objectives: list[str] = Field(default_factory=list)
    scope: dict[str, list[str]] = Field(
        default_factory=lambda: {"in_scope": [], "out_of_scope": []}
    )
    functional_requirements: list[FunctionalRequirement] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    similar_projects: list[SimilarProject] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    sources: list[str] = Field(default_factory=list)
