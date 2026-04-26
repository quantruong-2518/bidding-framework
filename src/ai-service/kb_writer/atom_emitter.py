"""Wave 2A — write requirement atoms to the bid vault.

Each atom lands at ``<vault>/bids/<bid_id>/requirements/<atom_id>.md`` with:

* YAML frontmatter from :class:`AtomFrontmatter` (Pydantic ``model_dump``).
* Body markdown (the H1 + content_markdown the extractor produced).

Per Conv-15 atomicity convention: write to a sibling ``.tmp-`` file, then
``os.replace`` into place. Per-atom failures are isolated — one bad atom
doesn't block the rest of the batch (mirrors :mod:`kb_writer.kb_delta`).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from kb_writer.models import WorkspaceReceipt
from workflows.base import AtomFrontmatter

logger = logging.getLogger(__name__)

REQUIREMENTS_SUBDIR = "requirements"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(atom_id: str) -> str:
    """Force a filesystem-safe filename. Atom ids are already ``REQ-F-001`` shape
    but we sanitise defensively in case a custom extractor produces colons /
    spaces / unicode."""
    slug = _SLUG_RE.sub("-", (atom_id or "").strip()).strip("-").lower()
    return f"{slug or 'atom'}.md"


def _render_atom_body(atom: AtomFrontmatter, body_md: str) -> str:
    """Compose YAML frontmatter + body. We hand-roll the YAML so we can match
    ``kb_writer.kb_delta`` style without dragging in a full YAML dumper.
    """
    extraction_block = "\n".join(
        [
            "extraction:",
            f"  parser: {atom.extraction.parser}",
            f"  confidence: {atom.extraction.confidence:.4f}",
            f"  extracted_at: {atom.extraction.extracted_at.isoformat()}",
        ]
    )
    source_block_lines = [
        "source:",
        f"  file: {atom.source.file}",
    ]
    if atom.source.section is not None:
        source_block_lines.append(f"  section: {atom.source.section}")
    if atom.source.page is not None:
        source_block_lines.append(f"  page: {atom.source.page}")
    if atom.source.line_range is not None:
        source_block_lines.append(
            f"  line_range: [{atom.source.line_range[0]}, {atom.source.line_range[1]}]"
        )
    source_block = "\n".join(source_block_lines)

    verification_lines = ["verification:"]
    verification_lines.append(
        f"  verified_by: {atom.verification.verified_by or 'null'}"
    )
    verification_lines.append(
        f"  verified_at: {atom.verification.verified_at.isoformat() if atom.verification.verified_at else 'null'}"
    )
    verification_block = "\n".join(verification_lines)

    links_lines = ["links:"]
    links_lines.append(
        f"  depends_on: {json.dumps(list(atom.links.depends_on))}"
    )
    links_lines.append(
        f"  conflicts_with: {json.dumps(list(atom.links.conflicts_with))}"
    )
    links_lines.append(
        f"  refines: {atom.links.refines if atom.links.refines else 'null'}"
    )
    links_lines.append(
        f"  cross_ref: {json.dumps(list(atom.links.cross_ref))}"
    )
    links_block = "\n".join(links_lines)

    frontmatter_parts: list[str] = [
        "---",
        f"id: {atom.id}",
        f"type: {atom.type}",
        f"priority: {atom.priority}",
        f'category: "{atom.category}"',
        source_block,
        extraction_block,
        verification_block,
        links_block,
        f"tags: {json.dumps(list(atom.tags))}",
        f"tenant_id: {atom.tenant_id}",
        f"bid_id: {atom.bid_id}",
        f"role: {atom.role}",
        f"split_recommended: {'true' if atom.split_recommended else 'false'}",
        f"version: {atom.version}",
        f"supersedes: {atom.supersedes or 'null'}",
        f"superseded_by: {atom.superseded_by or 'null'}",
        f"active: {'true' if atom.active else 'false'}",
        f"ai_generated: {'true' if atom.ai_generated else 'false'}",
        f"approved: {'true' if atom.approved else 'false'}",
        "---",
        "",
    ]
    body = (body_md or atom.id).rstrip() + "\n"
    return "\n".join(frontmatter_parts) + body


# Public re-export so kb_writer.templates can borrow the same renderer.
def render_atom_body(atom: AtomFrontmatter, body_md: str) -> str:
    """Render one atom to its on-disk markdown body (frontmatter + content)."""
    return _render_atom_body(atom, body_md)


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


def write_atom(
    vault_root: str | Path,
    bid_id: str | UUID,
    atom: AtomFrontmatter,
    body_md: str,
) -> Path:
    """Write a single atom file. Returns the absolute path.

    Caller catches exceptions if it wants per-atom isolation; the batch
    helper :func:`write_atoms` does that for free.
    """
    root = Path(vault_root) / "bids" / str(bid_id) / REQUIREMENTS_SUBDIR
    target = root / _safe_filename(atom.id)
    content = _render_atom_body(atom, body_md)
    _write_atomic(target, content)
    return target


def write_atoms(
    vault_root: str | Path,
    bid_id: str | UUID,
    atoms: list[tuple[AtomFrontmatter, str]],
) -> WorkspaceReceipt:
    """Batch-write atoms with per-atom failure isolation.

    Mirror of :func:`kb_writer.kb_delta.write_kb_deltas` for the atom path.
    """
    receipt = WorkspaceReceipt(
        bid_id=str(bid_id),
        phase="S0_5_DONE",
        files_written=[],
        files_skipped=[],
        errors=[],
    )
    if not atoms:
        return receipt

    for atom, body_md in atoms:
        try:
            target = write_atom(vault_root, bid_id, atom, body_md)
            relative = str(target.relative_to(vault_root)) if Path(vault_root).exists() else str(target)
            receipt.files_written.append(relative)
        except Exception as exc:  # noqa: BLE001 — per-atom isolation
            receipt.errors.append(f"{atom.id}: {exc}")
            logger.warning(
                "atom_emitter.write_failed bid_id=%s atom_id=%s err=%s",
                bid_id,
                atom.id,
                exc,
            )
    logger.info(
        "atom_emitter.batch_done bid_id=%s written=%d errors=%d",
        bid_id,
        len(receipt.files_written),
        len(receipt.errors),
    )
    return receipt


__all__ = [
    "REQUIREMENTS_SUBDIR",
    "render_atom_body",
    "write_atom",
    "write_atoms",
]
