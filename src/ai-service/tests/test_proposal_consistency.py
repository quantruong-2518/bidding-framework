"""Phase 3.1 — proposal consistency checker tests.

Each check is exercised in isolation using mutated fixtures + a hand-built
section list where needed. The checker never raises — it reports a bool and
leaves the decision to the S9 review gate.
"""

from __future__ import annotations

from typing import Iterable

from assembly.consistency import check_consistency
from assembly.renderer import render_package
from tests.fixtures.bid_states import edge_bid, full_bid_m, minimal_bid_s
from workflows.artifacts import ProposalSection


def _sections_from(payload) -> list[ProposalSection]:
    return render_package(payload).sections


def _make_sections(bodies: Iterable[tuple[str, str]]) -> list[ProposalSection]:
    return [
        ProposalSection(heading=heading, body_markdown=body, sourced_from=[])
        for heading, body in bodies
    ]


def test_ba_coverage_passes_when_every_must_is_mentioned() -> None:
    payload = full_bid_m()
    sections = _sections_from(payload)
    checks = check_consistency(payload, sections)
    assert checks["ba_coverage"] is True


def test_ba_coverage_fails_when_must_title_missing_from_output() -> None:
    payload = full_bid_m()
    # Build a stub-only section list that does NOT mention REQ-001 anywhere.
    sections = _make_sections(
        [
            ("Cover Page", "Cover body without identifiers."),
            ("Executive Summary", "Generic summary."),
        ]
    )
    checks = check_consistency(payload, sections)
    assert checks["ba_coverage"] is False


def test_wbs_matches_pricing_true_on_full_bid_and_zero_pricing() -> None:
    full = full_bid_m()
    zero = edge_bid()
    assert check_consistency(full, _sections_from(full))["wbs_matches_pricing"] is True
    assert check_consistency(zero, _sections_from(zero))["wbs_matches_pricing"] is True


def test_wbs_matches_pricing_false_when_subtotal_drifts_from_lines() -> None:
    payload = full_bid_m()
    # Corrupt the subtotal so it no longer equals sum(lines).
    payload.pricing.subtotal = payload.pricing.subtotal + 123.45
    checks = check_consistency(payload, _sections_from(payload))
    assert checks["wbs_matches_pricing"] is False


def test_wbs_matches_pricing_true_when_pricing_absent_bid_s() -> None:
    payload = minimal_bid_s()
    assert payload.pricing is None
    checks = check_consistency(payload, _sections_from(payload))
    assert checks["wbs_matches_pricing"] is True


def test_client_name_consistent_true_when_client_in_cover_and_exec() -> None:
    payload = full_bid_m()
    checks = check_consistency(payload, _sections_from(payload))
    assert checks["client_name_consistent"] is True


def test_client_name_consistent_false_when_exec_drops_client() -> None:
    payload = full_bid_m()
    sections = _sections_from(payload)
    # Overwrite executive summary body to strip client name.
    for section in sections:
        if section.heading == "Executive Summary":
            section.body_markdown = "Summary text without the client placeholder."
    checks = check_consistency(payload, sections)
    assert checks["client_name_consistent"] is False


def test_rendered_all_sections_true_only_when_seven_sections_present() -> None:
    payload = full_bid_m()
    checks = check_consistency(payload, _sections_from(payload))
    assert checks["rendered_all_sections"] is True
    assert check_consistency(payload, [])["rendered_all_sections"] is False


def test_terminology_aligned_false_when_rival_terms_coexist() -> None:
    payload = full_bid_m()
    drift = _make_sections(
        [
            ("Cover Page", "The customer and the client share the same proposal."),
        ]
    )
    checks = check_consistency(payload, drift)
    assert checks["terminology_aligned"] is False


def test_terminology_aligned_true_on_clean_output() -> None:
    payload = full_bid_m()
    checks = check_consistency(payload, _sections_from(payload))
    assert checks["terminology_aligned"] is True
