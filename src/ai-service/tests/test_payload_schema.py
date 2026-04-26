"""S0.5 Wave 2C — per-role payload schema validation tests.

Pure-Pydantic specs. We override the autouse conftest fixtures locally so the
test does not pull in temporalio / kb-vault sandboxing for every assertion —
these specs touch only :mod:`rag.payload_schema`.
"""

from __future__ import annotations

import pytest

from rag.payload_schema import (
    AtomPayload,
    DerivedPayload,
    LessonPayload,
    SourcePayload,
    routes_to_prod,
    validate_payload,
)


# Override autouse conftest fixtures — the payload_schema module imports
# nothing from workflows / Temporal, so we don't need their setup.
@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401 — override conftest fixture
    """No-op override: payload_schema specs don't touch the workflow module."""
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    """No-op override: payload_schema specs never publish."""
    yield None


@pytest.fixture(autouse=True)
def _sandbox_kb_vault(tmp_path):
    """No-op override: payload_schema specs never write to the vault."""
    yield tmp_path


# ---------- per-role validators --------------------------------------------


def test_validate_source_payload_accepts_required_fields() -> None:
    """A minimal source payload validates and exposes its fields."""
    payload = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "source",
        "file_id": "01-rfp-main",
        "section": None,
        "chunk_idx": 0,
    }
    validated = validate_payload(payload, "source")
    assert isinstance(validated, SourcePayload)
    assert validated.tenant_id == "acme"
    assert validated.file_id == "01-rfp-main"
    assert validated.chunk_idx == 0
    # Sources never route to prod regardless of any other flag.
    assert routes_to_prod(validated) is False


def test_validate_atom_payload_routes_to_prod_when_approved_and_active() -> None:
    """Approved + active atoms are the only payload that routes to PROD."""
    approved = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "requirement_atom",
        "atom_id": "REQ-F-001",
        "atom_type": "functional",
        "priority": "MUST",
        "approved": True,
        "active": True,
        "category": "user_management",
        "source_file": "sources/01-rfp-main.md",
        "tags": ["banking", "auth"],
    }
    validated = validate_payload(approved, "requirement_atom")
    assert isinstance(validated, AtomPayload)
    assert validated.atom_id == "REQ-F-001"
    assert validated.priority == "MUST"
    assert validated.tags == ["banking", "auth"]
    assert routes_to_prod(validated) is True

    # Same atom but approved=False stays in staging.
    pending = {**approved, "approved": False}
    pending_validated = validate_payload(pending, "requirement_atom")
    assert isinstance(pending_validated, AtomPayload)
    assert routes_to_prod(pending_validated) is False

    # Approved but superseded (active=False) also stays in staging.
    superseded = {**approved, "active": False}
    superseded_validated = validate_payload(superseded, "requirement_atom")
    assert isinstance(superseded_validated, AtomPayload)
    assert routes_to_prod(superseded_validated) is False


def test_validate_derived_payload_requires_kind() -> None:
    """Derived artefacts must declare which file kind they represent."""
    payload = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "derived",
        "kind": "compliance_matrix",
    }
    validated = validate_payload(payload, "derived")
    assert isinstance(validated, DerivedPayload)
    assert validated.kind == "compliance_matrix"
    # Derived payloads NEVER route to prod (only atoms gate that surface).
    assert routes_to_prod(validated) is False


def test_validate_lesson_payload_carries_outcome() -> None:
    """Conv-15 lessons carry the bid outcome to enable retrospective filtering."""
    payload = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "lesson",
        "outcome": "WON",
        "kb_delta_id": "delta-42",
    }
    validated = validate_payload(payload, "lesson")
    assert isinstance(validated, LessonPayload)
    assert validated.outcome == "WON"
    assert validated.kb_delta_id == "delta-42"
    # Lessons never route to prod (atoms-only gate).
    assert routes_to_prod(validated) is False


# ---------- failure modes --------------------------------------------------


def test_validate_payload_rejects_missing_required_field() -> None:
    """A payload missing a required field returns None, not raises."""
    bad_atom = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "requirement_atom",
        # missing atom_id, atom_type, priority, approved, active.
    }
    assert validate_payload(bad_atom, "requirement_atom") is None

    bad_source = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "source",
        # missing file_id and chunk_idx.
    }
    assert validate_payload(bad_source, "source") is None


def test_validate_payload_unknown_role_returns_none() -> None:
    """Unknown roles are silently rejected; caller falls back to staging."""
    payload = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "wat",
    }
    assert validate_payload(payload, "wat") is None


def test_validate_payload_accepts_extra_legacy_fields() -> None:
    """Existing legacy payload keys (content / chunk_index / client / …)
    must flow through the typed model without rejection (Rule B)."""
    payload = {
        "tenant_id": "acme",
        "bid_id": "bid-001",
        "role": "source",
        "file_id": "01-rfp-main",
        "chunk_idx": 0,
        # legacy / informational keys that ride on every chunk:
        "content": "...",
        "parent_doc_id": "01-rfp-main",
        "chunk_index": 0,
        "client": "Acme",
        "domain": "banking",
        "doc_type": "rfp",
        "source_path": "/vault/bids/bid-001/sources/01-rfp-main.md",
    }
    validated = validate_payload(payload, "source")
    assert isinstance(validated, SourcePayload)
    # Extra fields preserved on the model (extra="allow").
    assert getattr(validated, "client", None) == "Acme"
