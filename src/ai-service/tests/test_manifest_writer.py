"""S0.5 Wave 2A — manifest_writer unit tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from kb_writer.manifest_writer import MANIFEST_FILENAME, write_manifest
from workflows.base import Manifest, ManifestFile


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def _make_manifest() -> Manifest:
    return Manifest(
        version=1,
        bid_id=str(uuid4()),
        tenant_id="acme-bank",
        session_id=str(uuid4()),
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        files=[
            ManifestFile(
                file_id="01-rfp-main",
                original_name="Banking_Core_RFP_v1.pdf",
                mime="application/pdf",
                sha256="abc123",
                size_bytes=2_450_123,
                page_count=87,
                role="rfp",
                language="en",
                parsed_to="sources/01-rfp-main.md",
                atoms_extracted=142,
                extraction_confidence_avg=0.87,
            )
        ],
        parser_version="rfp_extractor_v2.1",
        synth_version="synth_v1.0",
    )


def test_write_manifest_creates_file_at_expected_path(tmp_path: Path) -> None:
    bid_id = uuid4()
    manifest = _make_manifest()
    target = write_manifest(tmp_path, bid_id, manifest)
    assert target.exists()
    assert target.name == MANIFEST_FILENAME
    assert target.parent.name == str(bid_id)


def test_write_manifest_serialises_files_and_metadata(tmp_path: Path) -> None:
    bid_id = uuid4()
    manifest = _make_manifest()
    target = write_manifest(tmp_path, bid_id, manifest)
    payload = json.loads(target.read_text())
    assert payload["version"] == 1
    assert payload["tenant_id"] == "acme-bank"
    assert payload["parser_version"] == "rfp_extractor_v2.1"
    assert len(payload["files"]) == 1
    assert payload["files"][0]["role"] == "rfp"
    assert payload["files"][0]["atoms_extracted"] == 142


def test_write_manifest_overwrites_existing_atomically(tmp_path: Path) -> None:
    bid_id = uuid4()
    manifest = _make_manifest()
    write_manifest(tmp_path, bid_id, manifest)

    # Mutate + rewrite — should fully replace.
    updated = manifest.model_copy(
        update={"parser_version": "rfp_extractor_v3.0"}
    )
    write_manifest(tmp_path, bid_id, updated)

    target = tmp_path / "bids" / str(bid_id) / MANIFEST_FILENAME
    payload = json.loads(target.read_text())
    assert payload["parser_version"] == "rfp_extractor_v3.0"
    # No leftover .tmp- files.
    siblings = list(target.parent.glob(".tmp-*"))
    assert siblings == []


def test_write_manifest_handles_empty_files_list(tmp_path: Path) -> None:
    bid_id = uuid4()
    manifest = Manifest(bid_id="b", tenant_id="t", session_id="s")
    target = write_manifest(tmp_path, bid_id, manifest)
    payload = json.loads(target.read_text())
    assert payload["files"] == []
