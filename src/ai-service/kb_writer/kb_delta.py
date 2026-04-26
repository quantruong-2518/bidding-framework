"""Conv 15 — write retrospective KBDeltas to the Obsidian vault.

Each delta lands at ``<vault>/lessons/<bid_id>-<delta_id>.md`` with
``ai_generated: true`` frontmatter so a downstream reviewer can approve /
reject before the next ingestion run promotes it into the real KB. Writes
are atomic (temp-file + ``os.replace``) so a crashed run never leaves a
half-written note in the vault.

This is the "AI → vault" half of the bi-directional sync. The "vault → AI"
half is already covered by ``ingestion/`` which re-indexes any user-edited
note into Qdrant on the next watcher tick.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from kb_writer.models import WorkspaceReceipt
from rag.tenant import SHARED_TENANT
from workflows.artifacts import KBDelta

logger = logging.getLogger(__name__)

LESSONS_SUBDIR = "lessons"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_slug(value: str) -> str:
    """Force a filesystem-safe slug; fall back to ``delta`` on empty input."""
    slug = _SLUG_RE.sub("-", (value or "").strip()).strip("-").lower()
    return slug or "delta"


def _delta_filename(bid_id: UUID, delta: KBDelta) -> str:
    """Vault-relative filename. Always under ``lessons/`` regardless of target_path."""
    return f"{LESSONS_SUBDIR}/{bid_id}-{_safe_slug(delta.id)}.md"


def _render_delta(bid_id: UUID, delta: KBDelta, *, tenant_id: str) -> str:
    """Compose the markdown body — frontmatter + the LLM's content_markdown.

    ``ai_generated: true`` is the load-bearing flag: ingestion sees it and
    holds the delta out of the prod KB until a reviewer flips ``approved``.
    """
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    frontmatter = "\n".join(
        [
            "---",
            f"bid_id: {bid_id}",
            f"delta_id: {delta.id}",
            f"delta_type: {delta.type}",
            f"ai_generated: {'true' if delta.ai_generated else 'false'}",
            f"approved: {'true' if delta.approved else 'false'}",
            f"tenant_id: {tenant_id}",
            f"generated_at: {generated_at}",
            f'title: "{delta.title}"',
            f'rationale: "{delta.rationale.replace(chr(34), chr(39))}"',
            "---",
            "",
        ]
    )
    body = delta.content_markdown.rstrip() + "\n"
    return frontmatter + body


def _write_atomic(path: Path, content: str) -> None:
    """Same temp-then-replace contract as :func:`kb_writer.bid_workspace._write_atomic`."""
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


def write_kb_deltas(
    vault_root: str | Path,
    bid_id: UUID,
    deltas: list[KBDelta],
    *,
    tenant_id: str = SHARED_TENANT,
) -> WorkspaceReceipt:
    """Persist each delta to the vault. Per-delta failures land in ``errors``."""
    receipt = WorkspaceReceipt(
        bid_id=str(bid_id),
        phase="S11_DONE",
        files_written=[],
        files_skipped=[],
        errors=[],
    )
    if not deltas:
        return receipt

    root = Path(vault_root)
    for delta in deltas:
        filename = _delta_filename(bid_id, delta)
        target = root / filename
        try:
            content = _render_delta(bid_id, delta, tenant_id=tenant_id)
            _write_atomic(target, content)
            receipt.files_written.append(filename)
            logger.info(
                "kb_delta.write bid_id=%s delta_id=%s path=%s",
                bid_id,
                delta.id,
                filename,
            )
        except Exception as exc:  # noqa: BLE001 — per-delta failure isolation
            receipt.errors.append(f"{filename}: {exc}")
            logger.warning(
                "kb_delta.write_failed bid_id=%s delta_id=%s err=%s",
                bid_id,
                delta.id,
                exc,
            )
    return receipt


__all__ = ["write_kb_deltas", "LESSONS_SUBDIR"]
