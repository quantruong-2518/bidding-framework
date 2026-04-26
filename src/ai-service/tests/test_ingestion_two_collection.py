"""S0.5 Wave 2C — ingestion two-collection routing tests.

Verifies that the ingestion pipeline derives ``role`` + ``approved`` + ``active``
from frontmatter / path and asks the indexer to route between
``bid-atoms-staging`` and ``bid-atoms-prod`` accordingly.

The tests inject a fake indexer (a callable matching the IngestionService
contract) so we never load Qdrant, fastembed, or any LLM client. Every
assertion lands on the captured ``__collection__`` hint plus the metadata
overrides — exactly what :func:`rag.indexer.index_documents` consumes when
routing in ``"auto"`` mode.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from config.ingestion import IngestionSettings
from ingestion.ingestion_service import IngestionService


# Override autouse conftest fixtures — these tests don't load Temporal or
# Redis. The default ``_compress_gate_timeouts`` would import workflows.bid_workflow
# which transitively pulls in ``temporalio``; that module is not installed
# on every host, so we shadow the fixture with a no-op.
@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401 — override conftest fixture
    """No-op override: ingestion specs don't touch the workflow module."""
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    """No-op override: ingestion specs never publish."""
    yield None


@pytest.fixture(autouse=True)
def _sandbox_kb_vault(tmp_path):
    """No-op override: each test creates its own vault under tmp_path."""
    yield tmp_path


# ---------- helpers --------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def _settings(tmp_path: Path, root: Path) -> IngestionSettings:
    return IngestionSettings(
        vault_path=root,
        poll_interval_seconds=0.05,
        debounce_ms=50,
        hash_cache_path=tmp_path / "hashes.json",
        graph_snapshot_path=tmp_path / "graph.json",
    )


def _make_recording_indexer():
    """Return ``(callable, calls)`` where calls accumulates `(path, overrides)`."""
    calls: list[tuple[str, dict]] = []

    async def fake_indexer(client, path, metadata_overrides):
        calls.append((path, dict(metadata_overrides or {})))
        return 1  # pretend 1 chunk indexed

    return fake_indexer, calls


def _find_call(calls: list[tuple[str, dict]], suffix: str) -> dict:
    """Return the overrides dict for the first call whose path ends with ``suffix``."""
    for path, overrides in calls:
        if path.endswith(suffix):
            return overrides
    raise AssertionError(f"no recorded indexer call for path suffix={suffix!r} (got {calls})")


# ---------- specs ----------------------------------------------------------


@pytest.mark.asyncio
async def test_atom_approved_routes_to_auto_collection(tmp_path: Path) -> None:
    """approved + active atom must be routed via collection=auto for prod-eligible upsert."""
    root = tmp_path / "vault"
    _write(
        root / "bids" / "bid-acme-001" / "requirements" / "REQ-F-001.md",
        """
        ---
        id: REQ-F-001
        type: functional
        priority: MUST
        category: user_management
        tenant_id: acme
        bid_id: bid-acme-001
        approved: true
        active: true
        ---
        # User Management
        Users SHALL log in with SSO.
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    await service.initial_index(root)

    overrides = _find_call(calls, "REQ-F-001.md")
    assert overrides["role"] == "requirement_atom"
    assert overrides["atom_type"] == "functional"
    assert overrides["priority"] == "MUST"
    assert overrides["approved"] is True
    assert overrides["active"] is True
    assert overrides["tenant_id"] == "acme"
    assert overrides["bid_id"] == "bid-acme-001"
    # The hint that triggers staging-vs-prod routing in index_documents.
    assert overrides["__collection__"] == "auto"


@pytest.mark.asyncio
async def test_atom_pending_review_stays_in_staging(tmp_path: Path) -> None:
    """approved=false (or missing) atoms still get role tagged but route to staging."""
    root = tmp_path / "vault"
    _write(
        root / "bids" / "bid-acme-001" / "requirements" / "REQ-F-002.md",
        """
        ---
        id: REQ-F-002
        type: functional
        priority: SHOULD
        tenant_id: acme
        bid_id: bid-acme-001
        ---
        # Drafted but not yet approved
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    await service.initial_index(root)

    overrides = _find_call(calls, "REQ-F-002.md")
    assert overrides["role"] == "requirement_atom"
    # Default-safe values from the ingestion service: not yet approved.
    assert overrides["approved"] is False
    assert overrides["active"] is True
    # The auto router will see approved=False AND choose staging.
    assert overrides["__collection__"] == "auto"


@pytest.mark.asyncio
async def test_source_role_always_routes_to_auto(tmp_path: Path) -> None:
    """Source markdown under bids/<id>/sources/ never qualifies for prod."""
    root = tmp_path / "vault"
    _write(
        root / "bids" / "bid-acme-001" / "sources" / "01-rfp-main.md",
        """
        ---
        tenant_id: acme
        bid_id: bid-acme-001
        file_id: 01-rfp-main
        ---
        # RFP — Banking Core Modernization
        Section 3.2 — Users SHALL log in via SSO.
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    await service.initial_index(root)

    overrides = _find_call(calls, "01-rfp-main.md")
    assert overrides["role"] == "source"
    assert overrides["bid_id"] == "bid-acme-001"
    assert overrides["__collection__"] == "auto"
    # ``approved`` / ``active`` fields are NOT populated for sources — the
    # router relies on role to keep them in staging.
    assert "approved" not in overrides


@pytest.mark.asyncio
async def test_derived_kind_inferred_from_filename(tmp_path: Path) -> None:
    """compliance_matrix.md / risks etc. infer role=derived + kind=<filename_stem>."""
    root = tmp_path / "vault"
    _write(
        root / "bids" / "bid-acme-001" / "compliance_matrix.md",
        """
        ---
        tenant_id: acme
        bid_id: bid-acme-001
        ---
        # Compliance matrix
        | Req | Status |
        | --- | --- |
        | REQ-F-001 | met |
        """,
    )
    _write(
        root / "bids" / "bid-acme-001" / "risk_register.md",
        """
        ---
        tenant_id: acme
        bid_id: bid-acme-001
        ---
        # Risks
        - Vendor lock-in.
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    await service.initial_index(root)

    cm = _find_call(calls, "compliance_matrix.md")
    assert cm["role"] == "derived"
    assert cm["kind"] == "compliance_matrix"
    assert cm["__collection__"] == "auto"

    rr = _find_call(calls, "risk_register.md")
    assert rr["role"] == "derived"
    assert rr["kind"] == "risk_register"


@pytest.mark.asyncio
async def test_lesson_layout_derives_lesson_role(tmp_path: Path) -> None:
    """Conv-15 layout: clients/<tenant>/lessons/*.md → role=lesson, tenant from path."""
    root = tmp_path / "vault"
    _write(
        root / "clients" / "acme" / "lessons" / "bid-001-delta-1.md",
        """
        ---
        bid_id: bid-001
        outcome: WON
        kb_delta_id: delta-1
        ai_generated: true
        ---
        # Lesson learned: SSO time-budget.
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    await service.initial_index(root)

    overrides = _find_call(calls, "bid-001-delta-1.md")
    assert overrides["role"] == "lesson"
    assert overrides["outcome"] == "WON"
    assert overrides["tenant_id"] == "acme"  # derived from clients/acme/...
    assert overrides["bid_id"] == "bid-001"
    assert overrides["__collection__"] == "auto"


@pytest.mark.asyncio
async def test_legacy_note_without_role_routes_to_legacy_collection(tmp_path: Path) -> None:
    """A frontmatter without ``role`` (pre-S0.5) keeps landing in the legacy collection.

    This is the safety knob that prevents accidental prod pollution: when a
    legacy seed note lives under ``technologies/`` or root-level, it has no
    role and the indexer pins it to ``"legacy"`` — never staging, never prod.
    """
    root = tmp_path / "vault"
    _write(
        root / "technologies" / "microservices.md",
        """
        ---
        domain: architecture
        doc_type: technology
        ---
        # Microservices
        Cross-cutting reference note.
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    await service.initial_index(root)

    overrides = _find_call(calls, "microservices.md")
    assert overrides.get("role") is None
    # Default-fallback per design doc: legacy notes never silently leak to prod.
    assert overrides["__collection__"] == "legacy"
    assert overrides["tenant_id"] == "shared"


@pytest.mark.asyncio
async def test_drafts_subtree_skipped_by_scanner(tmp_path: Path) -> None:
    """``_drafts/`` and ``packs/`` directories must be skipped during the scan.

    Half-written atoms parked in ``_drafts/`` would otherwise get indexed
    and pollute the staging collection before the parser finishes.
    """
    root = tmp_path / "vault"
    _write(
        root / "bids" / "bid-acme-001" / "_drafts" / "REQ-F-999.md",
        """
        ---
        id: REQ-F-999
        type: functional
        priority: MUST
        tenant_id: acme
        bid_id: bid-acme-001
        ---
        # Half-written
        """,
    )
    _write(
        root / "bids" / "bid-acme-001" / "packs" / "ba-pack.md",
        """
        ---
        tenant_id: acme
        bid_id: bid-acme-001
        ---
        # BA pack snapshot — should not be indexed (regenerated on demand).
        """,
    )
    # And a real atom alongside the skipped trees so we know the scan ran.
    _write(
        root / "bids" / "bid-acme-001" / "requirements" / "REQ-F-001.md",
        """
        ---
        id: REQ-F-001
        type: functional
        priority: MUST
        tenant_id: acme
        bid_id: bid-acme-001
        approved: false
        active: true
        ---
        # Real atom
        """,
    )

    indexer, calls = _make_recording_indexer()
    service = IngestionService(
        qdrant_client=object(),
        settings=_settings(tmp_path, root),
        indexer=indexer,
    )
    indexed = await service.initial_index(root)

    # Only the real atom indexed — the _drafts and packs subtrees are walled off.
    # We assert against the path *segments* below the vault root so that an
    # ancestor path containing the substring (e.g. /tmp/.../test_drafts_…) does
    # not produce a false positive.
    relatives = [Path(p).relative_to(root).parts for p, _ in calls]
    assert indexed == 1
    assert any(rel[-1] == "REQ-F-001.md" for rel in relatives)
    assert not any("_drafts" in rel for rel in relatives)
    assert not any("packs" in rel for rel in relatives)
