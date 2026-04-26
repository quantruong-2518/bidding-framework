"""S0.5 Wave 2A — pack_builder unit tests.

Covers: filter by type/tag, dirty flag flip, idempotent rebuild, CLI surface.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from kb_writer.atom_emitter import write_atom
from kb_writer.pack_builder import (
    PACKS_SUBDIR,
    REQUIREMENTS_SUBDIR,
    STATUS_FILENAME,
    _atom_set_hash,
    _read_atoms,
    main,
    rebuild_packs,
)
from workflows.base import (
    AtomExtraction,
    AtomFrontmatter,
    AtomLinks,
    AtomSource,
    AtomVerification,
)


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def _make_atom(idx: int, atom_type: str, *, active: bool = True) -> AtomFrontmatter:
    type_prefix = {
        "functional": "F",
        "nfr": "NFR",
        "technical": "T",
        "compliance": "C",
        "timeline": "TL",
        "unclear": "U",
    }[atom_type]
    return AtomFrontmatter(
        id=f"REQ-{type_prefix}-{idx:03d}",
        type=atom_type,  # type: ignore[arg-type]
        priority="MUST",
        category="general",
        source=AtomSource(file="sources/01-rfp.md"),
        extraction=AtomExtraction(
            parser="heuristic_v1",
            confidence=0.5,
            extracted_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        ),
        verification=AtomVerification(),
        links=AtomLinks(),
        tenant_id="acme",
        bid_id="session-1",
        active=active,
    )


def _populate_vault(tmp_path: Path, bid_id: str) -> None:
    """Drop a few atoms across multiple types into the vault."""
    write_atom(tmp_path, bid_id, _make_atom(1, "functional"), "Functional one body")
    write_atom(tmp_path, bid_id, _make_atom(2, "functional"), "Functional two body")
    write_atom(tmp_path, bid_id, _make_atom(1, "nfr"), "NFR one body")
    write_atom(tmp_path, bid_id, _make_atom(1, "technical"), "Tech one body")
    write_atom(tmp_path, bid_id, _make_atom(1, "compliance"), "Compliance one body")
    write_atom(tmp_path, bid_id, _make_atom(1, "timeline"), "Timeline one body")


def test_rebuild_packs_creates_expected_files(tmp_path: Path) -> None:
    bid_id = uuid4()
    _populate_vault(tmp_path, str(bid_id))
    rebuild_packs(tmp_path, str(bid_id))
    packs_dir = tmp_path / "bids" / str(bid_id) / PACKS_SUBDIR
    assert (packs_dir / "ba-pack.md").exists()
    assert (packs_dir / "sa-pack.md").exists()
    assert (packs_dir / "domain-pack.md").exists()
    assert (packs_dir / "pricing-pack.md").exists()
    assert (packs_dir / "review-pack.md").exists()
    assert (packs_dir / STATUS_FILENAME).exists()


def test_rebuild_packs_filters_atoms_by_type(tmp_path: Path) -> None:
    bid_id = uuid4()
    _populate_vault(tmp_path, str(bid_id))
    stats = rebuild_packs(tmp_path, str(bid_id))
    assert stats["ba-pack.md"].atoms_used == 2  # 2 functional
    assert stats["sa-pack.md"].atoms_used == 2  # 1 nfr + 1 technical
    assert stats["domain-pack.md"].atoms_used == 1
    assert stats["pricing-pack.md"].atoms_used == 1
    assert stats["review-pack.md"].atoms_used == 6  # all active


def test_rebuild_packs_excludes_inactive_atoms(tmp_path: Path) -> None:
    bid_id = uuid4()
    write_atom(tmp_path, bid_id, _make_atom(1, "functional", active=True), "active")
    write_atom(tmp_path, bid_id, _make_atom(2, "functional", active=False), "inactive")
    stats = rebuild_packs(tmp_path, bid_id)
    assert stats["review-pack.md"].atoms_used == 1
    assert stats["ba-pack.md"].atoms_used == 1


def test_rebuild_packs_writes_status_with_dirty_false(tmp_path: Path) -> None:
    bid_id = uuid4()
    _populate_vault(tmp_path, bid_id)
    rebuild_packs(tmp_path, bid_id)
    status_file = tmp_path / "bids" / str(bid_id) / PACKS_SUBDIR / STATUS_FILENAME
    payload = json.loads(status_file.read_text())
    assert payload["dirty"] is False
    assert payload["atom_set_hash"].startswith("sha256:")
    assert "packs" in payload
    assert "ba-pack.md" in payload["packs"]


def test_rebuild_packs_idempotent_on_same_inputs(tmp_path: Path) -> None:
    bid_id = uuid4()
    _populate_vault(tmp_path, bid_id)
    stats_first = rebuild_packs(tmp_path, bid_id)
    status_file = tmp_path / "bids" / str(bid_id) / PACKS_SUBDIR / STATUS_FILENAME
    hash_first = json.loads(status_file.read_text())["atom_set_hash"]

    stats_second = rebuild_packs(tmp_path, bid_id)
    hash_second = json.loads(status_file.read_text())["atom_set_hash"]
    assert hash_first == hash_second
    assert stats_first["ba-pack.md"].atoms_used == stats_second["ba-pack.md"].atoms_used


def test_rebuild_packs_no_atoms_produces_empty_packs(tmp_path: Path) -> None:
    bid_id = uuid4()
    stats = rebuild_packs(tmp_path, bid_id)
    for name in ("ba-pack.md", "sa-pack.md", "review-pack.md"):
        assert stats[name].atoms_used == 0
    review_path = tmp_path / "bids" / str(bid_id) / PACKS_SUBDIR / "review-pack.md"
    assert "_No atoms in this pack._" in review_path.read_text()


def test_atom_set_hash_changes_when_atom_body_changes(tmp_path: Path) -> None:
    bid_id = uuid4()
    write_atom(tmp_path, bid_id, _make_atom(1, "functional"), "Body A")
    atoms_root = tmp_path / "bids" / str(bid_id) / REQUIREMENTS_SUBDIR
    atoms = _read_atoms(atoms_root)
    h1 = _atom_set_hash(atoms)
    write_atom(tmp_path, bid_id, _make_atom(1, "functional"), "Body B")
    atoms2 = _read_atoms(atoms_root)
    h2 = _atom_set_hash(atoms2)
    assert h1 != h2


def test_main_cli_rebuild_packs_subcommand(tmp_path: Path) -> None:
    bid_id = uuid4()
    _populate_vault(tmp_path, bid_id)
    rc = main(["rebuild-packs", str(bid_id), "--vault", str(tmp_path)])
    assert rc == 0
    status_file = tmp_path / "bids" / str(bid_id) / PACKS_SUBDIR / STATUS_FILENAME
    assert status_file.exists()
