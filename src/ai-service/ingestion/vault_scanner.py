"""Recursively scan an Obsidian vault, yielding ParsedNote objects."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from ingestion.vault_parser import ParsedNote, parse_note

logger = logging.getLogger(__name__)

# S0.5 Wave 2C — additionally skip transient parser scratch dirs so half-written
# atoms / pre-confirm working copies / binary originals never reach Qdrant.
# ``_drafts`` and ``packs`` are referenced explicitly in the design doc §4
# (vault layout); ``_originals`` mirrors the MinIO backstop (Wave 1) for the
# rare local-fallback case.
_SKIP_DIR_NAMES = {
    ".obsidian",
    ".git",
    ".trash",
    "node_modules",
    "_drafts",
    "packs",
    "_originals",
}


def _iter_markdown_files(root: Path) -> list[Path]:
    """Walk the vault and return all .md files, skipping Obsidian internals."""
    results: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        results.append(path)
    return results


async def scan_vault(root: Path) -> AsyncIterator[ParsedNote]:
    """Yield a ParsedNote for every .md file under root (excluding .obsidian)."""
    root = root.resolve()
    if not root.exists():
        logger.warning("ingestion.scan_vault missing root=%s", root)
        return
    files = _iter_markdown_files(root)
    logger.info("ingestion.scan_vault root=%s files=%d", root, len(files))
    for path in files:
        try:
            yield parse_note(path, vault_root=root)
        except Exception as exc:  # noqa: BLE001 — keep scanning other notes
            logger.exception("ingestion.scan_vault parse_failed path=%s err=%s", path, exc)
