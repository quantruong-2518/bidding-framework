"""Wave 2A — pack regeneration script.

Reads the atom files under ``<vault>/bids/<bid_id>/requirements/`` and writes
agent-specific "packs" under ``<vault>/bids/<bid_id>/packs/``:

* ``ba-pack.md``      — functional + unclear atoms
* ``sa-pack.md``      — nfr + technical atoms
* ``domain-pack.md``  — compliance atoms
* ``pricing-pack.md`` — timeline atoms (informs commercial estimates)
* ``review-pack.md``  — every active atom (full review surface)

Status sidecar lives at ``packs/_status.json`` per §3.4 — tracks atom-set
hash + dirty flag so the watcher can skip re-builds when nothing changed.

CLI: ``python -m kb_writer rebuild-packs <bid_id> [--vault PATH]``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from workflows.base import AtomType

logger = logging.getLogger(__name__)

PACKS_SUBDIR = "packs"
REQUIREMENTS_SUBDIR = "requirements"
STATUS_FILENAME = "_status.json"

# Pack name → atom type filter. Multiple types allowed per pack — first hit
# decides which agent gets it; review-pack catches everything irrespective.
_PACK_FILTERS: dict[str, tuple[AtomType, ...]] = {
    "ba-pack.md": ("functional", "unclear"),
    "sa-pack.md": ("nfr", "technical"),
    "domain-pack.md": ("compliance",),
    "pricing-pack.md": ("timeline",),
    # review-pack is special — every active atom; handled separately.
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


class PackStats:
    """Per-pack rollup row in ``packs/_status.json::packs[name]``."""

    def __init__(self, atoms_used: int, tokens_est: int) -> None:
        self.atoms_used = atoms_used
        self.tokens_est = tokens_est

    def to_dict(self) -> dict[str, int]:
        return {"atoms_used": self.atoms_used, "tokens_est": self.tokens_est}


def _parse_atom_frontmatter(text: str) -> dict[str, str]:
    """Minimal YAML-ish parser — only handles ``key: value`` single lines.

    Same minimal subset md_adapter._strip_frontmatter handles. Sufficient for
    our atom files because we generate them ourselves with known shape.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    block = match.group(1)
    out: dict[str, str] = {}
    for line in block.splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            # Skip nested blocks (source: / extraction: / etc.) — pack builder
            # only needs top-level keys (id, type, priority, active, ...).
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _read_atoms(requirements_root: Path) -> list[dict[str, Any]]:
    """Parse every atom .md file under ``requirements/`` into a flat dict list."""
    atoms: list[dict[str, Any]] = []
    if not requirements_root.is_dir():
        return atoms
    for path in sorted(requirements_root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("pack_builder.read_failed path=%s err=%s", path, exc)
            continue
        front = _parse_atom_frontmatter(text)
        body = _FRONTMATTER_RE.sub("", text, count=1).strip()
        if not front:
            continue
        atoms.append({
            "id": front.get("id", ""),
            "type": front.get("type", "unclear"),
            "priority": front.get("priority", "SHOULD"),
            "active": front.get("active", "true").lower() == "true",
            "approved": front.get("approved", "false").lower() == "true",
            "category": front.get("category", "general"),
            "body": body,
            "path": path,
        })
    return atoms


def _atom_set_hash(atoms: list[dict[str, Any]]) -> str:
    """Stable content hash used by the dirty-flag check."""
    digest = hashlib.sha256()
    for atom in sorted(atoms, key=lambda a: a["id"]):
        digest.update(atom["id"].encode("utf-8"))
        digest.update(b"|")
        digest.update(atom["body"].encode("utf-8"))
        digest.update(b"|")
        digest.update(("active=1" if atom["active"] else "active=0").encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _render_pack(atoms: list[dict[str, Any]], *, title: str) -> str:
    """Compose one pack body from a filtered atom list."""
    if not atoms:
        return f"# {title}\n\n_No atoms in this pack._\n"
    lines: list[str] = [f"# {title}", ""]
    for atom in atoms:
        lines.append(
            f"## {atom['id']} — {atom['priority']} ({atom['type']})"
        )
        lines.append("")
        lines.append(atom["body"].rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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


def _filter_for_pack(atoms: list[dict[str, Any]], types: tuple[str, ...]) -> list[dict[str, Any]]:
    return [a for a in atoms if a["active"] and a["type"] in types]


def _estimate_tokens(text: str) -> int:
    """Cheap token-count proxy. ~4 chars / token holds for English; close
    enough for the dirty flag's tokens_est line."""
    return max(1, len(text) // 4)


def rebuild_packs(
    vault_root: str | Path,
    bid_id: str | UUID,
) -> dict[str, PackStats]:
    """Regenerate every pack for one bid. Idempotent — same atoms in = same packs out.

    Returns a dict of ``pack_filename -> PackStats`` reflecting the new state.
    Writes ``packs/_status.json`` with ``dirty=False`` after completion.
    """
    root = Path(vault_root) / "bids" / str(bid_id)
    requirements_root = root / REQUIREMENTS_SUBDIR
    packs_root = root / PACKS_SUBDIR

    atoms = _read_atoms(requirements_root)
    stats: dict[str, PackStats] = {}

    for pack_name, types in _PACK_FILTERS.items():
        filtered = _filter_for_pack(atoms, types)
        title = pack_name.removesuffix(".md").replace("-", " ").title()
        body = _render_pack(filtered, title=title)
        _write_atomic(packs_root / pack_name, body)
        stats[pack_name] = PackStats(
            atoms_used=len(filtered), tokens_est=_estimate_tokens(body)
        )

    # review-pack: every active atom (no type filter).
    review_atoms = [a for a in atoms if a["active"]]
    review_body = _render_pack(review_atoms, title="Review Pack")
    _write_atomic(packs_root / "review-pack.md", review_body)
    stats["review-pack.md"] = PackStats(
        atoms_used=len(review_atoms), tokens_est=_estimate_tokens(review_body)
    )

    status_payload = {
        "atom_set_hash": _atom_set_hash(atoms),
        "last_built_at": datetime.now(timezone.utc).isoformat(),
        "dirty": False,
        "packs": {name: s.to_dict() for name, s in stats.items()},
    }
    status_text = json.dumps(status_payload, indent=2, sort_keys=True) + "\n"
    _write_atomic(packs_root / STATUS_FILENAME, status_text)

    logger.info(
        "pack_builder.rebuild_done bid_id=%s atoms=%d packs=%d",
        bid_id,
        len(atoms),
        len(stats),
    )
    return stats


# ---------------------------------------------------------------------------
# CLI surface — invoked via `python -m kb_writer rebuild-packs <bid_id> [--vault]`
# (see ``__main__.py`` shim below).
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kb_writer", description="kb-vault pack management"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    rebuild = sub.add_parser("rebuild-packs", help="Regenerate ba/sa/domain/pricing/review packs")
    rebuild.add_argument("bid_id", help="Bid id (or parse session id)")
    rebuild.add_argument(
        "--vault",
        default=os.environ.get("KB_VAULT_PATH", "../kb-vault"),
        help="Vault root path (defaults to KB_VAULT_PATH or ../kb-vault)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.cmd != "rebuild-packs":
        parser.print_help()
        return 2
    stats = rebuild_packs(args.vault, args.bid_id)
    for name, st in stats.items():
        sys.stdout.write(f"{name}: atoms={st.atoms_used} tokens_est={st.tokens_est}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via CLI tests
    raise SystemExit(main())


__all__ = [
    "PACKS_SUBDIR",
    "STATUS_FILENAME",
    "PackStats",
    "rebuild_packs",
    "main",
]
