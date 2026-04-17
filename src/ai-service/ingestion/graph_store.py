"""Lightweight in-memory knowledge graph built from vault links."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ingestion.link_extractor import LinkEdge
from ingestion.vault_parser import ParsedNote

logger = logging.getLogger(__name__)


class GraphSnapshot(BaseModel):
    """Summary statistics for the current graph state."""

    note_count: int
    edge_count: int
    doc_types: dict[str, int] = Field(default_factory=dict)
    domains: dict[str, int] = Field(default_factory=dict)
    dangling_links: int = 0


class KnowledgeGraph:
    """In-memory graph: notes keyed by relative path, edges tracked both ways."""

    def __init__(self) -> None:
        self._nodes: dict[str, ParsedNote] = {}
        self._edges: list[LinkEdge] = []
        self._outgoing: dict[str, list[str]] = defaultdict(list)
        self._incoming: dict[str, list[str]] = defaultdict(list)

    def upsert_note(self, note: ParsedNote, edges: list[LinkEdge]) -> None:
        """Insert or replace a note and its outgoing edges."""
        key = str(note.relative_path)
        self._remove_outgoing(key)
        self._nodes[key] = note
        for edge in edges:
            self._edges.append(edge)
            self._outgoing[edge.source_path].append(edge.target_name)
            self._incoming[edge.target_name].append(edge.source_path)

    def _remove_outgoing(self, source_key: str) -> None:
        """Drop any existing outgoing edges from source_key before re-adding."""
        if source_key not in self._outgoing:
            return
        stale_targets = set(self._outgoing[source_key])
        self._edges = [e for e in self._edges if e.source_path != source_key]
        self._outgoing.pop(source_key, None)
        for target in stale_targets:
            self._incoming[target] = [s for s in self._incoming[target] if s != source_key]
            if not self._incoming[target]:
                self._incoming.pop(target, None)

    def note(self, relative_path: str) -> ParsedNote | None:
        """Return a note by its relative path, or None."""
        return self._nodes.get(relative_path)

    def neighbors(self, target_name: str) -> list[str]:
        """Return all source notes that link to target_name."""
        return list(self._incoming.get(target_name, []))

    def outgoing(self, source_path: str) -> list[str]:
        """Return all targets linked from source_path."""
        return list(self._outgoing.get(source_path, []))

    def snapshot(self) -> GraphSnapshot:
        """Compute summary stats over the current graph."""
        doc_types: dict[str, int] = defaultdict(int)
        domains: dict[str, int] = defaultdict(int)
        known_stems = {Path(k).stem for k in self._nodes}
        for note in self._nodes.values():
            fm = note.frontmatter
            dt = fm.get("doc_type")
            if isinstance(dt, str):
                doc_types[dt] += 1
            dm = fm.get("domain")
            if isinstance(dm, str):
                domains[dm] += 1
        dangling = sum(
            1
            for edge in self._edges
            if edge.target_name not in known_stems
            and f"{edge.target_name}.md" not in known_stems
        )
        return GraphSnapshot(
            note_count=len(self._nodes),
            edge_count=len(self._edges),
            doc_types=dict(doc_types),
            domains=dict(domains),
            dangling_links=dangling,
        )

    def as_dict(self) -> dict[str, Any]:
        """Dump graph to a JSON-friendly dict for persistence."""
        return {
            "nodes": [
                {
                    "relative_path": str(n.relative_path),
                    "frontmatter": n.frontmatter,
                    "headings": n.headings,
                    "links": n.links,
                    "content_hash": n.content_hash,
                }
                for n in self._nodes.values()
            ],
            "edges": [e.model_dump() for e in self._edges],
        }

    async def persist(self, destination: Path) -> Path:
        """Serialize the graph to destination as JSON; returns the written path."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        logger.info(
            "ingestion.graph_persist path=%s nodes=%d edges=%d",
            destination,
            len(self._nodes),
            len(self._edges),
        )
        return destination
