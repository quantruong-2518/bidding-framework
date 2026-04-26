"""Top-level ingestion orchestrator: scan -> parse -> index -> graph -> watch."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.ingestion import IngestionSettings, get_ingestion_settings
from ingestion.graph_store import KnowledgeGraph
from ingestion.link_extractor import build_edges
from ingestion.vault_parser import ParsedNote, parse_note
from ingestion.vault_scanner import scan_vault
from ingestion.watcher import VaultWatcher
from rag.tenant import (
    SHARED_TENANT,
    derive_tenant_id_from_relative_path,
    slugify,
)

logger = logging.getLogger(__name__)


def _frontmatter_to_overrides(note: ParsedNote) -> dict[str, Any]:
    """Translate a ParsedNote frontmatter into indexer metadata_overrides."""
    fm = note.frontmatter
    overrides: dict[str, Any] = {}
    for key in ("client", "domain", "project_id", "doc_type"):
        value = fm.get(key)
        if isinstance(value, str) and value:
            overrides[key] = value
    year = fm.get("year")
    if isinstance(year, int):
        overrides["year"] = year
    elif isinstance(year, str) and year.isdigit():
        overrides["year"] = int(year)
    overrides["source_path"] = str(note.path)
    if "project_id" in overrides:
        overrides["id"] = overrides["project_id"]
    else:
        overrides["id"] = note.path.stem
    # Phase 3.4-A: tenant_id is the multi-tenant filter column on Qdrant payload.
    # Frontmatter override wins; otherwise derive from kb-vault layout convention
    # (clients/<tenant>/... or legacy clients/<tenant>.md → tenant; else shared).
    fm_tenant = fm.get("tenant_id")
    if isinstance(fm_tenant, str) and fm_tenant.strip():
        overrides["tenant_id"] = slugify(fm_tenant) or SHARED_TENANT
    else:
        overrides["tenant_id"] = derive_tenant_id_from_relative_path(note.relative_path)
    return overrides


class IngestionService:
    """Orchestrates initial indexing, incremental re-indexing, and watching."""

    def __init__(
        self,
        qdrant_client: Any,
        *,
        settings: IngestionSettings | None = None,
        indexer: Any = None,
    ) -> None:
        self._client = qdrant_client
        self._settings = settings or get_ingestion_settings()
        self._graph = KnowledgeGraph()
        self._hashes: dict[str, str] = {}
        self._load_hash_cache()
        # Late-bind the indexer so tests can inject a stub without Qdrant.
        if indexer is None:
            from rag.indexer import index_markdown_file

            self._indexer = index_markdown_file
        else:
            self._indexer = indexer

    @property
    def graph(self) -> KnowledgeGraph:
        """Expose the in-memory knowledge graph for callers/tests."""
        return self._graph

    @property
    def settings(self) -> IngestionSettings:
        """Expose the active ingestion settings."""
        return self._settings

    def _load_hash_cache(self) -> None:
        """Load the per-path content-hash cache from disk if present."""
        cache = self._settings.hash_cache_path
        if not cache.exists():
            return
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._hashes = {str(k): str(v) for k, v in raw.items()}
                logger.info("ingestion.hash_cache_loaded entries=%d", len(self._hashes))
        except json.JSONDecodeError:
            logger.warning("ingestion.hash_cache_corrupt path=%s", cache)

    def _save_hash_cache(self) -> None:
        """Persist the per-path content-hash cache to disk."""
        cache = self._settings.hash_cache_path
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(self._hashes, indent=2), encoding="utf-8")

    async def _index_note(self, note: ParsedNote) -> int:
        """Run the configured indexer for a single parsed note."""
        overrides = _frontmatter_to_overrides(note)
        return await self._indexer(self._client, str(note.path), overrides)

    async def _process_note(self, note: ParsedNote) -> bool:
        """Index one note if its content hash has changed; update the graph."""
        key = str(note.path)
        if self._hashes.get(key) == note.content_hash:
            logger.debug("ingestion.skip_unchanged path=%s", key)
            self._graph.upsert_note(note, build_edges(note))
            return False
        chunks = await self._index_note(note)
        self._hashes[key] = note.content_hash
        self._graph.upsert_note(note, build_edges(note))
        logger.info("ingestion.indexed path=%s chunks=%s", note.relative_path, chunks)
        return True

    async def initial_index(self, vault_root: Path | None = None) -> int:
        """Scan the vault end-to-end, indexing changed notes and building edges."""
        root = (vault_root or self._settings.vault_path).resolve()
        logger.info("ingestion.initial_index root=%s", root)
        indexed = 0
        async for note in scan_vault(root):
            if await self._process_note(note):
                indexed += 1
        self._save_hash_cache()
        await self._graph.persist(self._settings.graph_snapshot_path)
        logger.info(
            "ingestion.initial_index_done indexed=%d total=%d",
            indexed,
            self._graph.snapshot().note_count,
        )
        return indexed

    async def on_file_change(self, path: Path) -> bool:
        """Re-parse and re-index a single file. Returns True if indexed."""
        if not path.exists():
            logger.info("ingestion.file_removed path=%s", path)
            self._hashes.pop(str(path), None)
            self._save_hash_cache()
            return False
        root = self._settings.vault_path.resolve()
        note = parse_note(path, vault_root=root)
        changed = await self._process_note(note)
        if changed:
            self._save_hash_cache()
            await self._graph.persist(self._settings.graph_snapshot_path)
        return changed

    async def run(self, vault_root: Path | None = None) -> None:
        """Initial index plus a live watcher; blocks until watcher stop()."""
        root = (vault_root or self._settings.vault_path).resolve()
        await self.initial_index(root)
        watcher = VaultWatcher(
            root,
            self.on_file_change,
            debounce_ms=self._settings.debounce_ms,
            poll_interval_seconds=self._settings.poll_interval_seconds,
        )
        logger.info("ingestion.watch_start root=%s", root)
        await watcher.watch()
