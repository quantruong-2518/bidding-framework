"""Phase 3.1 — proposal renderer tests (Jinja-backed output).

Tests use the fixtures in ``tests/fixtures/bid_states.py`` rather than
constructing bespoke payloads so renderer + consistency tests share one
source of truth. ``StrictUndefined`` in the Jinja env means a typo in a
template shows up here instead of at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assembly import (
    PROPOSAL_SECTIONS,
    RendererError,
    render_package,
    render_section,
)
from assembly.renderer import _build_env
from tests.fixtures.bid_states import (
    edge_bid,
    full_bid_m,
    minimal_bid_s,
)


def test_render_cover_section_emits_client_name() -> None:
    payload = full_bid_m()
    section = render_section("00-cover", "Cover Page", "bid_card", payload)
    assert section.heading == "Cover Page"
    assert "Acme Bank" in section.body_markdown
    assert "Prepared on" in section.body_markdown
    assert "Industry" in section.body_markdown


def test_render_package_returns_all_seven_sections() -> None:
    payload = full_bid_m()
    pkg = render_package(payload)
    headings = [s.heading for s in pkg.sections]
    assert headings == [heading for _, heading, _ in PROPOSAL_SECTIONS]
    assert pkg.consistency_checks["rendered_all_sections"] is True


def test_render_package_handles_bid_s_null_optionals() -> None:
    payload = minimal_bid_s()
    pkg = render_package(payload)
    headings = [s.heading for s in pkg.sections]
    assert "Technical Approach" in headings
    assert "Pricing + Commercials" in headings
    tech = next(s for s in pkg.sections if s.heading == "Technical Approach")
    pricing = next(s for s in pkg.sections if s.heading == "Pricing + Commercials")
    # Templates null-guard via section_or_na macro; Bid-S omits HLD + pricing.
    assert "Not applicable" in pricing.body_markdown
    # Tech approach still renders from SA draft even without HLD.
    assert "NestJS" in tech.body_markdown


def test_render_package_handles_edge_empty_wbs_and_zero_pricing() -> None:
    payload = edge_bid()
    pkg = render_package(payload)
    wbs = next(s for s in pkg.sections if s.heading == "WBS + Estimation")
    pricing = next(s for s in pkg.sections if s.heading == "Pricing + Commercials")
    # Empty WBS must still render a section body (not blow up) with a fallback.
    assert "Not applicable" in wbs.body_markdown or "No work" in wbs.body_markdown.lower() or len(wbs.body_markdown) > 0
    # Zero-subtotal pricing still renders a header.
    assert "Pricing" in pricing.body_markdown or "commercial" in pricing.body_markdown.lower()


def test_strict_undefined_catches_missing_variable(tmp_path: Path) -> None:
    """A template referencing a non-existent ctx var must raise RendererError."""
    # Seed a throwaway templates dir with one valid macros file + one broken template.
    (tmp_path / "_macros.md.j2").write_text("")
    (tmp_path / "broken.md.j2").write_text("{{ does_not_exist }}")
    env = _build_env(templates_dir=tmp_path)

    with pytest.raises(RendererError) as err:
        render_section("broken", "Broken", "test", full_bid_m(), env=env)
    assert "does_not_exist" in str(err.value) or "undefined" in str(err.value).lower()


def test_render_all_sections_produce_non_empty_body() -> None:
    payload = full_bid_m()
    pkg = render_package(payload)
    for section in pkg.sections:
        assert section.body_markdown.strip(), f"Section {section.heading} body is empty"
