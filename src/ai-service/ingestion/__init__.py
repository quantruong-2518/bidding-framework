"""Obsidian vault ingestion — parse markdown, extract links, index into Qdrant."""

from __future__ import annotations

from ingestion.graph_store import KnowledgeGraph
from ingestion.ingestion_service import IngestionService
from ingestion.link_extractor import LinkEdge, build_edges, extract_links
from ingestion.vault_parser import ParsedNote, parse_note
from ingestion.vault_scanner import scan_vault
from ingestion.watcher import VaultWatcher

__all__ = [
    "IngestionService",
    "KnowledgeGraph",
    "LinkEdge",
    "ParsedNote",
    "VaultWatcher",
    "build_edges",
    "extract_links",
    "parse_note",
    "scan_vault",
]
