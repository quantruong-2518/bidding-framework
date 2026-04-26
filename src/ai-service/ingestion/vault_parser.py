"""Parse a single Obsidian markdown note into a structured ParsedNote.

S0.5 Wave 2C extension:
* :class:`ParsedNote` exposes a derived ``role`` (and helper attributes) from
  the new vault layout. We add ``derived_role``, ``derived_kind``, and
  ``derived_bid_id`` fields populated by :func:`derive_role_metadata` from
  the vault-relative path. This is purely additive — every existing field
  stays untouched and ``derived_role`` is never required by older callers.

Path conventions (per design doc §4):
* ``bids/<bid_id>/requirements/<atom_id>.md``        → role=requirement_atom
* ``bids/<bid_id>/sources/<file_id>.md``             → role=source
* ``bids/<bid_id>/compliance_matrix.md``             → role=derived, kind=compliance_matrix
* ``bids/<bid_id>/win_themes.md``                    → role=derived, kind=win_themes
* ``bids/<bid_id>/risk_register.md``                 → role=derived, kind=risk_register
* ``bids/<bid_id>/open_questions.md``                → role=derived, kind=open_questions
* ``bids/<bid_id>/conflicts.md``                     → role=derived, kind=conflicts
* ``clients/<tenant>/lessons/<bid>-<delta>.md``      → role=lesson (Conv-15)
* anything else                                      → role=None  (legacy)

Frontmatter ``role:`` always wins over the path-derived value (lets reviewer
upgrade an atom to ``requirement_atom`` even outside the canonical layout).
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")

# File stems under bids/<bid_id>/ that resolve to a derived artefact (role=derived).
_DERIVED_FILENAME_KINDS: dict[str, str] = {
    "compliance_matrix": "compliance_matrix",
    "win_themes": "win_themes",
    "risk_register": "risk_register",
    "open_questions": "open_questions",
    "conflicts": "conflicts",
}


class ParsedNote(BaseModel):
    """Structured representation of a parsed Obsidian note."""

    path: Path
    relative_path: Path
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    content_hash: str

    # S0.5 Wave 2C — additive metadata derived from the vault layout. Every
    # field is optional; callers that don't care about role-aware indexing
    # (e.g. legacy seed scripts) can ignore them entirely.
    derived_role: str | None = None
    derived_kind: str | None = None
    derived_bid_id: str | None = None

    model_config = {"arbitrary_types_allowed": True}


def _parse_scalar(raw: str) -> Any:
    """Coerce a YAML scalar value into int/float/bool/str."""
    v = raw.strip().strip('"').strip("'")
    if not v:
        return ""
    lower = v.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def _parse_list_literal(raw: str) -> list[Any]:
    """Parse a simple inline list literal like `[a, b, c]`."""
    inner = raw.strip().lstrip("[").rstrip("]").strip()
    if not inner:
        return []
    return [_parse_scalar(p) for p in inner.split(",")]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a tiny subset of YAML frontmatter (key: value + inline lists)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm_block, body = match.group(1), match.group(2)
    fm: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in fm_block.splitlines():
        if not line.strip():
            current_list_key = None
            continue
        list_item = _LIST_ITEM_RE.match(line)
        if list_item and current_list_key is not None:
            fm[current_list_key].append(_parse_scalar(list_item.group(1)))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            fm[key] = []
            current_list_key = key
            continue
        if value.startswith("["):
            fm[key] = _parse_list_literal(value)
            current_list_key = None
            continue
        fm[key] = _parse_scalar(value)
        current_list_key = None
    return fm, body


def _extract_headings(body: str) -> list[str]:
    """Return all markdown headings in order of appearance."""
    return [m.group(2).strip() for m in _HEADING_RE.finditer(body)]


def _extract_wiki_links(body: str) -> list[str]:
    """Extract Obsidian-style [[target]] / [[target|alias]] link targets."""
    from ingestion.link_extractor import extract_links

    return extract_links(body)


def derive_role_metadata(
    relative_path: Path | str,
    frontmatter: dict[str, Any] | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Map a vault-relative path + frontmatter to ``(role, kind, bid_id)``.

    Frontmatter ``role`` is the override and wins over path-derived role.
    Returns ``(None, None, None)`` for legacy paths (root-level notes, etc.)
    so the indexer's default fallback (staging only, never prod) kicks in.
    """
    fm = frontmatter or {}
    parts = Path(relative_path).parts

    # Path-derived defaults --------------------------------------------------
    derived_role: str | None = None
    derived_kind: str | None = None
    derived_bid_id: str | None = None

    if parts and parts[0] == "bids" and len(parts) >= 2:
        derived_bid_id = parts[1]
        if len(parts) >= 3:
            sub = parts[2]
            stem = Path(parts[-1]).stem
            if sub == "requirements":
                derived_role = "requirement_atom"
            elif sub == "sources":
                derived_role = "source"
            elif sub.endswith(".md") and stem in _DERIVED_FILENAME_KINDS:
                # bids/<bid_id>/<derived>.md (file directly under bid root).
                derived_role = "derived"
                derived_kind = _DERIVED_FILENAME_KINDS[stem]
        else:
            stem = Path(parts[-1]).stem
            if stem in _DERIVED_FILENAME_KINDS:
                derived_role = "derived"
                derived_kind = _DERIVED_FILENAME_KINDS[stem]
    elif (
        len(parts) >= 4
        and parts[0] == "clients"
        and parts[2] == "lessons"
    ):
        derived_role = "lesson"

    # Frontmatter override ---------------------------------------------------
    fm_role = fm.get("role") if isinstance(fm.get("role"), str) else None
    if fm_role:
        derived_role = fm_role
    fm_kind = fm.get("kind") if isinstance(fm.get("kind"), str) else None
    if fm_kind:
        derived_kind = fm_kind
    fm_bid = fm.get("bid_id") if isinstance(fm.get("bid_id"), str) else None
    if fm_bid:
        derived_bid_id = fm_bid

    return derived_role, derived_kind, derived_bid_id


def parse_note(path: Path, vault_root: Path | None = None) -> ParsedNote:
    """Parse a single markdown note from disk into a ParsedNote."""
    raw = path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(raw)
    root = vault_root or path.parent
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    role, kind, bid_id = derive_role_metadata(rel, fm)
    note = ParsedNote(
        path=path,
        relative_path=rel,
        content=body,
        frontmatter=fm,
        links=_extract_wiki_links(body),
        headings=_extract_headings(body),
        content_hash=content_hash,
        derived_role=role,
        derived_kind=kind,
        derived_bid_id=bid_id,
    )
    logger.debug(
        "ingestion.parse_note path=%s links=%d headings=%d role=%s kind=%s",
        rel,
        len(note.links),
        len(note.headings),
        role,
        kind,
    )
    return note


__all__ = [
    "ParsedNote",
    "derive_role_metadata",
    "parse_note",
]
