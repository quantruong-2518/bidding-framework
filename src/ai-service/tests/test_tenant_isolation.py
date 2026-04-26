"""Phase 3.4-A — multi-tenant isolation: slug + path derivation + Qdrant filter + kb_search."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from rag.retriever import build_qdrant_filter
from rag.tenant import (
    SHARED_TENANT,
    derive_tenant_id_from_path,
    derive_tenant_id_from_relative_path,
    slugify,
)


# --- slugify ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Acme Bank", "acme-bank"),
        ("  AcmeCorp  ", "acmecorp"),
        ("Mệkông Telecom!", "m-k-ng-telecom"),
        ("ACME / Holdings, Inc.", "acme-holdings-inc"),
        ("", ""),
    ],
)
def test_slugify_lowercases_and_collapses_non_alnum(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


# --- derive_tenant_id -------------------------------------------------------


def test_derive_tenant_id_from_relative_path_matrix() -> None:
    """Per Phase 3.4-A convention: clients/<tenant>/... → tenant; else → shared."""
    assert (
        derive_tenant_id_from_relative_path(Path("clients/acme/projects/a.md"))
        == "acme"
    )
    # legacy flat layout
    assert derive_tenant_id_from_relative_path(Path("clients/medix.md")) == "medix"
    # everything else
    assert derive_tenant_id_from_relative_path(Path("lessons/risk.md")) == SHARED_TENANT
    assert (
        derive_tenant_id_from_relative_path(Path("technologies/microservices.md"))
        == SHARED_TENANT
    )
    assert (
        derive_tenant_id_from_relative_path(Path("bids/abc/proposal.md"))
        == SHARED_TENANT
    )
    assert derive_tenant_id_from_relative_path(Path("README.md")) == SHARED_TENANT


def test_derive_tenant_id_from_path_uses_vault_root(tmp_path: Path) -> None:
    """Absolute-path variant resolves vs vault_root and falls through to shared."""
    vault = tmp_path / "kb"
    (vault / "clients" / "acme").mkdir(parents=True)
    note = vault / "clients" / "acme" / "intro.md"
    note.write_text("# hi", encoding="utf-8")
    assert derive_tenant_id_from_path(note, vault) == "acme"

    # path outside the vault root → shared (defensive default).
    outside = tmp_path / "elsewhere.md"
    outside.write_text("hi", encoding="utf-8")
    assert derive_tenant_id_from_path(outside, vault) == SHARED_TENANT


def test_derive_tenant_slugifies_directory_names() -> None:
    """Tenant directories may have spaces/case — slug result must be filesafe."""
    assert (
        derive_tenant_id_from_relative_path(Path("clients/Acme Bank/intro.md"))
        == "acme-bank"
    )


# --- Qdrant filter ----------------------------------------------------------


def test_build_qdrant_filter_tenant_list_yields_should_clauses() -> None:
    """A list value on tenant_id maps to OR'd Qdrant `should` conditions."""
    qfilter = build_qdrant_filter({"tenant_id": ["acme", SHARED_TENANT]})
    assert qfilter is not None
    should_keys = [c.key for c in (qfilter.should or [])]
    # one should clause per OR'd value.
    assert should_keys.count("tenant_id") == 2


def test_build_qdrant_filter_tenant_scalar_is_must() -> None:
    """A scalar tenant_id is a hard `must` filter (no shared fall-through)."""
    qfilter = build_qdrant_filter({"tenant_id": "acme"})
    assert qfilter is not None
    must_keys = [c.key for c in (qfilter.must or [])]
    assert must_keys == ["tenant_id"]
    assert not (qfilter.should or [])


# --- kb_search contract -----------------------------------------------------


@pytest.mark.asyncio
async def test_kb_search_rejects_empty_tenant_id() -> None:
    """tenant_id is mandatory — we'd rather crash than silently leak."""
    from tools.kb_search import kb_search

    with pytest.raises(ValueError, match="tenant_id"):
        await kb_search(query="banking api", tenant_id="")
    with pytest.raises(ValueError, match="tenant_id"):
        await kb_search(query="banking api", tenant_id="   ")


@pytest.mark.asyncio
async def test_kb_search_passes_tenant_plus_shared_filter_to_retriever() -> None:
    """include_shared=True (default) widens the search to tenant + shared payloads."""
    from tools import kb_search as kb_search_mod

    captured: dict = {}

    async def fake_search(client, request):
        captured["filters"] = dict(request.filters)
        return []

    with (
        patch.object(kb_search_mod, "_lazy_client", AsyncMock(return_value=object())),
        patch.object(kb_search_mod, "search", fake_search),
    ):
        await kb_search_mod.kb_search(
            query="banking api", tenant_id="acme-bank", domain="Banking"
        )

    assert captured["filters"]["tenant_id"] == ["acme-bank", SHARED_TENANT]
    # domain still flows + lowercased, so existing behaviour is preserved.
    assert captured["filters"]["domain"] == "banking"


@pytest.mark.asyncio
async def test_kb_search_include_shared_false_locks_to_tenant() -> None:
    """Strict mode: no shared fall-through — useful for tenant-only audits."""
    from tools import kb_search as kb_search_mod

    captured: dict = {}

    async def fake_search(client, request):
        captured["filters"] = dict(request.filters)
        return []

    with (
        patch.object(kb_search_mod, "_lazy_client", AsyncMock(return_value=object())),
        patch.object(kb_search_mod, "search", fake_search),
    ):
        await kb_search_mod.kb_search(
            query="banking api",
            tenant_id="acme-bank",
            include_shared=False,
        )

    assert captured["filters"]["tenant_id"] == "acme-bank"


@pytest.mark.asyncio
async def test_kb_search_returns_empty_when_qdrant_unavailable() -> None:
    """A dead Qdrant must NOT bypass the tenant filter — caller sees empty hits."""
    from tools import kb_search as kb_search_mod

    with patch.object(kb_search_mod, "_lazy_client", AsyncMock(return_value=None)):
        hits = await kb_search_mod.kb_search(query="x", tenant_id="acme-bank")
    assert hits == []
