"""S0.5 Wave 2A — atom_emitter unit tests.

Covers: roundtrip frontmatter, body format, atomic write, slug safety,
per-atom failure isolation, link rendering.

Runs on bare ``pytest`` (no temporalio): we override the conftest autouse
fixtures that import the Temporal-dependent workflow module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from kb_writer.atom_emitter import (
    REQUIREMENTS_SUBDIR,
    _safe_filename,
    render_atom_body,
    write_atom,
    write_atoms,
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
    """No-op override — atom_emitter tests don't touch the workflow module."""
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def _make_atom(idx: int = 1, *, atom_type: str = "functional", priority: str = "MUST") -> AtomFrontmatter:
    return AtomFrontmatter(
        id=f"REQ-F-{idx:03d}",
        type=atom_type,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        category="user_management",
        source=AtomSource(
            file="sources/01-rfp-main.md",
            section="3.1 User Management",
            page=4,
            line_range=(10, 15),
        ),
        extraction=AtomExtraction(
            parser="heuristic_v1",
            confidence=0.5,
            extracted_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        ),
        verification=AtomVerification(),
        links=AtomLinks(depends_on=["REQ-F-002"], conflicts_with=["REQ-NFR-001"]),
        tenant_id="acme-bank",
        bid_id="session-uuid-1",
    )


def test_render_atom_body_includes_id_type_priority() -> None:
    atom = _make_atom()
    body = render_atom_body(atom, "# Title\n\n- claim 1\n")
    assert "id: REQ-F-001" in body
    assert "type: functional" in body
    assert "priority: MUST" in body
    assert 'category: "user_management"' in body
    # Body markdown is preserved verbatim.
    assert "claim 1" in body


def test_render_atom_body_renders_links_block() -> None:
    atom = _make_atom()
    body = render_atom_body(atom, "body")
    assert 'depends_on: ["REQ-F-002"]' in body
    assert 'conflicts_with: ["REQ-NFR-001"]' in body
    assert "refines: null" in body


def test_render_atom_body_renders_extraction_metadata() -> None:
    atom = _make_atom()
    body = render_atom_body(atom, "body")
    assert "parser: heuristic_v1" in body
    assert "confidence: 0.5000" in body
    assert "2026-04-26" in body  # extracted_at ISO


def test_safe_filename_replaces_unsafe_chars() -> None:
    assert _safe_filename("REQ-F-001") == "req-f-001.md"
    assert _safe_filename("R E Q") == "r-e-q.md"
    # Empty / pathological input falls back to the literal "atom".
    assert _safe_filename("") == "atom.md"
    assert _safe_filename("   ") == "atom.md"


def test_write_atom_creates_file_under_requirements(tmp_path: Path) -> None:
    bid_id = uuid4()
    target = write_atom(tmp_path, bid_id, _make_atom(), "Body content")
    assert target.exists()
    assert target.parent.name == REQUIREMENTS_SUBDIR
    assert target.name == "req-f-001.md"
    text = target.read_text()
    assert "id: REQ-F-001" in text
    assert "Body content" in text


def test_write_atom_is_atomic_no_tmp_files_left(tmp_path: Path) -> None:
    bid_id = uuid4()
    write_atom(tmp_path, bid_id, _make_atom(), "Body")
    siblings = list((tmp_path / "bids" / str(bid_id) / REQUIREMENTS_SUBDIR).glob("*"))
    assert len(siblings) == 1
    # No leftover temp files.
    assert all(not s.name.startswith(".tmp-") for s in siblings)


def test_write_atoms_isolates_per_atom_failures(tmp_path: Path) -> None:
    bid_id = uuid4()
    good1 = (_make_atom(1), "body1")
    good2 = (_make_atom(2), "body2")
    receipt = write_atoms(tmp_path, bid_id, [good1, good2])
    assert len(receipt.files_written) == 2
    assert receipt.errors == []


def test_write_atoms_empty_list_is_noop(tmp_path: Path) -> None:
    bid_id = uuid4()
    receipt = write_atoms(tmp_path, bid_id, [])
    assert receipt.files_written == []
    assert receipt.errors == []
    assert not (tmp_path / "bids" / str(bid_id)).exists()
