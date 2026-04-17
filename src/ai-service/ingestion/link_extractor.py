"""Extract [[wiki-links]] from markdown and build edges for the knowledge graph."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from ingestion.vault_parser import ParsedNote

logger = logging.getLogger(__name__)

_WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
_CONTEXT_WINDOW = 80


class LinkEdge(BaseModel):
    """A single directed edge from one note to a link target."""

    source_path: str
    target_name: str
    context: str


def _normalize_target(raw: str) -> str:
    """Strip whitespace and path prefixes from a wiki-link target."""
    target = raw.strip()
    # Obsidian allows "folder/target" — keep only the final segment as the name.
    if "/" in target:
        target = target.rsplit("/", 1)[-1]
    # Drop a trailing .md if the author wrote one.
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target


def extract_links(text: str) -> list[str]:
    """Return the list of normalized link targets found in text."""
    targets: list[str] = []
    for match in _WIKI_LINK_RE.finditer(text):
        targets.append(_normalize_target(match.group(1)))
    return targets


def _snippet_around(text: str, start: int, end: int) -> str:
    """Return a short single-line context snippet centered on the link."""
    left = max(0, start - _CONTEXT_WINDOW)
    right = min(len(text), end + _CONTEXT_WINDOW)
    return " ".join(text[left:right].split())


def build_edges(note: ParsedNote) -> list[LinkEdge]:
    """Build LinkEdge objects for every wiki-link in the note body."""
    edges: list[LinkEdge] = []
    source = str(note.relative_path)
    for match in _WIKI_LINK_RE.finditer(note.content):
        target = _normalize_target(match.group(1))
        edges.append(
            LinkEdge(
                source_path=source,
                target_name=target,
                context=_snippet_around(note.content, match.start(), match.end()),
            )
        )
    logger.debug("ingestion.build_edges source=%s edges=%d", source, len(edges))
    return edges
