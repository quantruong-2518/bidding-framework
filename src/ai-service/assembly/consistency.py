"""Phase 3.1 — cheap cross-section consistency checks.

Runs after :func:`assembly.renderer.render_package` builds all seven sections.
Each check returns a bool; results land in
``ProposalPackage.consistency_checks`` and are surfaced in the frontend
:component:`ProposalPanel`.

Failure of a check does NOT fail the activity — the review gate (S9) decides
what to do with a flagged proposal.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — type-only imports
    from workflows.artifacts import AssemblyInput, ProposalSection

logger = logging.getLogger(__name__)


def check_consistency(
    payload: "AssemblyInput",
    sections: list["ProposalSection"],
) -> dict[str, bool]:
    """Aggregate all consistency checks into a single dict."""
    return {
        "ba_coverage": _check_ba_coverage(payload, sections),
        "wbs_matches_pricing": _check_wbs_matches_pricing(payload),
        "client_name_consistent": _check_client_name_consistent(payload, sections),
        "rendered_all_sections": len(sections) == 7,
        "terminology_aligned": _check_terminology_aligned(sections),
    }


def _check_ba_coverage(
    payload: "AssemblyInput",
    sections: list["ProposalSection"],
) -> bool:
    """Every MUST functional requirement from the BA draft is mentioned somewhere."""
    ba = payload.ba_draft
    musts = [
        fr for fr in getattr(ba, "functional_requirements", []) or []
        if getattr(fr, "priority", None) == "MUST"
    ]
    if not musts:
        return True
    haystack = "\n".join(s.body_markdown for s in sections).lower()
    for fr in musts:
        needle = (getattr(fr, "id", "") or "").lower()
        if needle and needle in haystack:
            continue
        title_needle = (getattr(fr, "title", "") or "").lower().strip()
        if title_needle and title_needle in haystack:
            continue
        return False
    return True


def _check_wbs_matches_pricing(payload: "AssemblyInput") -> bool:
    """Pricing total == subtotal * (1 + margin/100), within a cent."""
    pricing = payload.pricing
    if pricing is None:
        return True  # Bid-S skips commercials by design.
    if not pricing.lines:
        return pricing.subtotal == 0 and pricing.total == 0
    line_sum = sum(line.amount for line in pricing.lines)
    if abs(line_sum - pricing.subtotal) > 0.01:
        return False
    expected_total = pricing.subtotal * (1.0 + (pricing.margin_pct or 0.0) / 100.0)
    return abs(expected_total - pricing.total) <= 0.01


def _check_client_name_consistent(
    payload: "AssemblyInput",
    sections: list["ProposalSection"],
) -> bool:
    """The client name appears in at least the cover + exec summary."""
    bid = payload.bid_card
    client_name = (getattr(bid, "client_name", None) or "").strip()
    if not client_name:
        return True
    required_headings = {"Cover Page", "Executive Summary"}
    for section in sections:
        if section.heading in required_headings and client_name.lower() not in section.body_markdown.lower():
            return False
    return True


_TERMINOLOGY_PAIRS: tuple[tuple[str, str], ...] = (
    # Catch two sections disagreeing on the same concept. Not exhaustive —
    # just cheap heuristics that have caught drift in past bids.
    ("solution", "system"),
    ("customer", "client"),
)


def _check_terminology_aligned(sections: list["ProposalSection"]) -> bool:
    """Flag when the same concept is described with two rival terms in the same body."""
    for section in sections:
        body = section.body_markdown.lower()
        for left, right in _TERMINOLOGY_PAIRS:
            if _has_word(body, left) and _has_word(body, right):
                return False
    return True


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


__all__ = ["check_consistency"]
