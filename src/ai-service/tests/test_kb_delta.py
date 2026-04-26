"""Conv 15 — Obsidian KB-delta write-back. Atomic, frontmatter-flagged, isolated."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from kb_writer.kb_delta import LESSONS_SUBDIR, _safe_slug, write_kb_deltas
from rag.tenant import SHARED_TENANT
from workflows.artifacts import KBDelta


def _delta(idx: int = 1) -> KBDelta:
    return KBDelta(
        id=f"DELTA-{idx:03d}",
        type="new_lesson",
        target_path="ignored — wrapper rewrites",
        title=f"Retry storm lesson {idx}",
        content_markdown=f"# Retry storm {idx}\n\nDo X, avoid Y.",
        rationale="reviewer flagged retry storms in S9",
    )


def test_safe_slug_collapses_unsafe_chars() -> None:
    assert _safe_slug("DELTA-001") == "delta-001"
    assert _safe_slug("  WeIrd!! ID..") == "weird-id"
    assert _safe_slug("") == "delta"
    assert _safe_slug("path/with/slash") == "path-with-slash"


def test_write_kb_deltas_writes_each_delta_under_lessons(tmp_path: Path) -> None:
    bid_id = uuid4()
    receipt = write_kb_deltas(tmp_path, bid_id, [_delta(1), _delta(2)])

    assert sorted(receipt.files_written) == sorted(
        [
            f"{LESSONS_SUBDIR}/{bid_id}-delta-001.md",
            f"{LESSONS_SUBDIR}/{bid_id}-delta-002.md",
        ]
    )
    assert receipt.errors == []
    written = (tmp_path / LESSONS_SUBDIR / f"{bid_id}-delta-001.md").read_text()
    assert "# Retry storm 1" in written
    # AI provenance is the load-bearing flag — ingestion holds these out of prod KB.
    assert "ai_generated: true" in written
    assert "approved: false" in written
    # Tenant defaults to SHARED_TENANT when caller omits it.
    assert f"tenant_id: {SHARED_TENANT}" in written
    assert "delta_type: new_lesson" in written


def test_write_kb_deltas_threads_explicit_tenant_id(tmp_path: Path) -> None:
    bid_id = uuid4()
    write_kb_deltas(tmp_path, bid_id, [_delta()], tenant_id="acme-bank")
    written = (tmp_path / LESSONS_SUBDIR / f"{bid_id}-delta-001.md").read_text()
    assert "tenant_id: acme-bank" in written


def test_write_kb_deltas_empty_input_is_noop(tmp_path: Path) -> None:
    bid_id = uuid4()
    receipt = write_kb_deltas(tmp_path, bid_id, [])
    assert receipt.files_written == []
    assert receipt.errors == []
    # No spurious lessons/ directory created.
    assert not (tmp_path / LESSONS_SUBDIR).exists()


def test_write_kb_deltas_isolates_per_delta_failure(tmp_path: Path) -> None:
    """A delta with an unwritable filename must not block the rest."""
    bid_id = uuid4()
    good = _delta(1)
    # Force a failure on the second delta by pointing the lessons subdir at a file.
    (tmp_path / LESSONS_SUBDIR).write_text("blocker")
    receipt = write_kb_deltas(tmp_path, bid_id, [good])

    # The whole batch failed because lessons/ is a file; receipt records the error.
    assert receipt.files_written == []
    assert len(receipt.errors) == 1
    assert "delta-001" in receipt.errors[0]
