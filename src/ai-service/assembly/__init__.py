"""Phase 3.1 — proposal package assembly.

The :mod:`activities.assembly` Temporal wrapper delegates to
:func:`assembly.renderer.render_package`, which Jinja-renders each of the
seven proposal sections from the current :class:`workflows.artifacts.AssemblyInput`.
Rendering is best-effort: a :class:`RendererError` in ``render_package``
triggers the activity-level stub fallback so the bid never fails on a
templating glitch.
"""

from __future__ import annotations

from assembly.consistency import check_consistency
from assembly.renderer import (
    PROPOSAL_SECTIONS,
    RendererError,
    render_package,
    render_section,
)

__all__ = [
    "PROPOSAL_SECTIONS",
    "RendererError",
    "check_consistency",
    "render_package",
    "render_section",
]
