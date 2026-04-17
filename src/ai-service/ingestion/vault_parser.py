"""Parse a single Obsidian markdown note into a structured ParsedNote."""

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


class ParsedNote(BaseModel):
    """Structured representation of a parsed Obsidian note."""

    path: Path
    relative_path: Path
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    content_hash: str

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
    note = ParsedNote(
        path=path,
        relative_path=rel,
        content=body,
        frontmatter=fm,
        links=_extract_wiki_links(body),
        headings=_extract_headings(body),
        content_hash=content_hash,
    )
    logger.debug(
        "ingestion.parse_note path=%s links=%d headings=%d",
        rel,
        len(note.links),
        len(note.headings),
    )
    return note
