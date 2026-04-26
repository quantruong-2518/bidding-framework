"""Wave 2A — write ``_manifest.json`` for one bid workspace.

The manifest is the audit summary: which files were uploaded, what role they
were classified as, parser version, atom counts, plus the object-store URIs
for the originals (binary blobs live in MinIO per Decision #3, NOT git).

Atomic write — temp + rename — same contract as :mod:`kb_writer.atom_emitter`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from workflows.base import Manifest

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "_manifest.json"


def _serialise(manifest: Manifest) -> dict[str, Any]:
    """Dump to a JSON-friendly dict; datetimes ISO-stringified."""
    payload = manifest.model_dump(mode="json")
    return payload


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def write_manifest(
    vault_root: str | Path,
    bid_id: str | UUID,
    manifest: Manifest,
) -> Path:
    """Persist a Manifest at ``<vault>/bids/<bid_id>/_manifest.json``.

    Returns the absolute path. Caller wraps in try/except if it wants
    per-bid isolation (workflow does — see :mod:`activities.context_synthesis`).
    """
    root = Path(vault_root) / "bids" / str(bid_id)
    target = root / MANIFEST_FILENAME
    payload = _serialise(manifest)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _write_atomic(target, content)
    logger.info(
        "manifest_writer.done bid_id=%s files=%d path=%s",
        bid_id,
        len(manifest.files),
        target,
    )
    return target


__all__ = ["MANIFEST_FILENAME", "write_manifest"]
