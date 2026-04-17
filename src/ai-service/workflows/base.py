"""Shared primitive types used by both workflow state models and agent I/O.

This module intentionally has zero imports from `workflows.models`,
`workflows.artifacts`, or `agents.*`. It sits at the bottom of the dependency
graph so the higher-level modules (which DO depend on each other) can all
import from here without triggering import cycles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

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
    "S9_BLOCKED",
    "S10",
    "S11",
    "S11_DONE",
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


def utcnow() -> datetime:
    """Module-local helper so callers don't need to remember the timezone arg."""
    return datetime.now(timezone.utc)


class RequirementAtom(BaseModel):
    """A single decomposed requirement with its category + trace source."""

    id: str
    text: str
    category: RequirementCategory
    source_section: str | None = None
