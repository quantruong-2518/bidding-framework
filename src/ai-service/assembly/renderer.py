"""Phase 3.1 Jinja-backed proposal renderer.

Produces the seven-section :class:`ProposalPackage` from an
:class:`AssemblyInput`. Templates live in
``src/ai-service/templates/proposal/``; each section is a standalone
``.md.j2`` file that receives the shared context documented in
``project_phase_3_1_detailed_plan.md``.

Design notes:

- :class:`RendererError` wraps :class:`jinja2.TemplateError` so the activity
  wrapper catches a single app-level type. Stub-fallback lives in the activity.
- ``StrictUndefined`` is enabled in the Jinja env so typos in templates fail
  loud in unit tests; production still benefits because the activity swallows
  the RendererError + emits the stub fallback + flips
  ``consistency_checks["rendered_all_sections"] = False``.
- Null-guarding for optional fields (HLD on Bid-S, pricing on Bid-S) is done
  in the templates themselves via ``{% if hld %}`` — the renderer does not
  pre-filter. A section that resolves to empty body emits a visible
  ``Not applicable`` placeholder via the ``section_or_na`` macro.
- Template lookup is pinned to the packaged ``templates/proposal`` directory
  so behavior is identical across Docker + local dev.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from workflows.artifacts import (
    AssemblyInput,
    ProposalPackage,
    ProposalSection,
)

logger = logging.getLogger(__name__)

PROPOSAL_SECTIONS: tuple[tuple[str, str, str], ...] = (
    # (template_stem, section_heading, sourced_from_tag)
    ("00-cover", "Cover Page", "bid_card"),
    ("01-executive-summary", "Executive Summary", "ba_draft"),
    ("02-business-requirements", "Business Requirements", "ba_draft"),
    ("03-technical-approach", "Technical Approach", "sa_draft"),
    ("04-wbs-estimation", "WBS + Estimation", "wbs"),
    ("05-pricing-commercials", "Pricing + Commercials", "pricing"),
    ("06-terms-appendix", "Terms + Appendix", "domain_notes"),
)


class RendererError(Exception):
    """Raised when Jinja rendering fails for any section."""


def _templates_dir() -> Path:
    """Resolve the packaged templates directory.

    Kept as a function so tests can monkeypatch when they want to point at a
    throwaway template tree (e.g. to inject a broken template).
    """
    return Path(__file__).resolve().parent.parent / "templates" / "proposal"


def _build_env(templates_dir: Path | None = None) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir or _templates_dir())),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["currency"] = _filter_currency
    env.filters["date"] = _filter_date
    return env


def _filter_currency(value: Any, symbol: str = "USD") -> str:
    if value is None:
        return "TBD"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{amount:,.2f} {symbol}"


def _filter_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    """Render a datetime in ``fmt``.

    Defensive on input shape because Temporal's ``pydantic_data_converter``
    serializes ``AssemblyInput.bid_card`` / ``triage`` / ``scoping``
    (typed ``Any`` to dodge the models↔artifacts import cycle) into plain
    dicts with ISO-8601 datetime strings — we want the same ``YYYY-MM-DD``
    output on both the unit-test path (raw datetime) and the activity path
    (ISO string).
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, str):
        try:
            # Python's fromisoformat accepts "+00:00" offsets in 3.11+.
            return datetime.fromisoformat(value).strftime(fmt)
        except ValueError:
            return value
    return str(value)


def _build_context(payload: AssemblyInput) -> dict[str, Any]:
    """Compose the shared template context. All fields nullable per D8."""
    generated_at = payload.generated_at or datetime.now(timezone.utc)
    return {
        "title": payload.title,
        "bid": payload.bid_card,
        "triage": payload.triage,
        "scoping": payload.scoping,
        "ba": payload.ba_draft,
        "sa": payload.sa_draft,
        "domain": payload.domain_notes,
        "convergence": payload.convergence,
        "hld": payload.hld,
        "wbs": payload.wbs,
        "pricing": payload.pricing,
        "reviews": payload.reviews or [],
        "today": generated_at,
    }


def render_section(
    template_stem: str,
    heading: str,
    sourced_from: str,
    payload: AssemblyInput,
    *,
    env: Environment | None = None,
) -> ProposalSection:
    """Render a single section. Raises :class:`RendererError` on Jinja failure."""
    jenv = env or _build_env()
    try:
        template = jenv.get_template(f"{template_stem}.md.j2")
        body = template.render(**_build_context(payload))
    except TemplateError as exc:  # noqa: BLE001 — unified app error type
        raise RendererError(
            f"Template {template_stem}.md.j2 failed: {exc.__class__.__name__}: {exc}"
        ) from exc
    return ProposalSection(
        heading=heading,
        body_markdown=body.strip() + "\n",
        sourced_from=[sourced_from] if sourced_from else [],
    )


def render_package(payload: AssemblyInput) -> ProposalPackage:
    """Render all seven proposal sections; raises :class:`RendererError` on failure."""
    from assembly.consistency import check_consistency  # local — avoid cycle

    env = _build_env()
    sections: list[ProposalSection] = []
    for stem, heading, source in PROPOSAL_SECTIONS:
        section = render_section(stem, heading, source, payload, env=env)
        sections.append(section)

    checks = check_consistency(payload, sections)
    # `rendered_all_sections` is always True here — if any template failed we
    # would have raised RendererError before reaching this point.
    checks.setdefault("rendered_all_sections", True)

    return ProposalPackage(
        bid_id=payload.bid_id,
        title=payload.title,
        sections=sections,
        appendices=["Assumptions (BA)", "Risk register (BA + SA)"],
        consistency_checks=checks,
    )


__all__ = [
    "PROPOSAL_SECTIONS",
    "RendererError",
    "render_package",
    "render_section",
]
