"""Tests for the artifact-level ACL map.

Pure-Python module — no Temporal / Redis / KB side effects. The autouse
fixtures from `tests/conftest.py` that import `workflows.bid_workflow`
(Temporal-dependent) are opted out via local overrides below, so this file
can run on a bare `pytest` without `temporalio` installed.
"""

from __future__ import annotations

import pytest

from workflows.acl import (
    ALL_ARTIFACT_KEYS,
    ALL_ROLES,
    ARTIFACT_ACL,
    acl_as_json,
    has_access,
    visible_artifacts,
)


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401 — override conftest fixture
    """No-op override: ACL tests don't touch the workflow module."""

    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    """No-op override: ACL tests never publish."""

    yield None


@pytest.fixture(autouse=True)
def _sandbox_kb_vault(tmp_path):
    """No-op override: ACL tests never write to the vault."""

    yield tmp_path


def test_admin_sees_every_artifact() -> None:
    for key in ALL_ARTIFACT_KEYS:
        assert has_access({"admin"}, key) is True


def test_admin_wildcard_bypasses_unknown_key() -> None:
    # admin is global — even an unlisted key resolves True (useful when new
    # artifacts land mid-migration).
    assert has_access({"admin"}, "future_artifact_not_in_map") is True


def test_non_admin_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        has_access({"ba"}, "no_such_artifact")


def test_role_intersection_resolves() -> None:
    assert has_access({"ba"}, "ba_draft") is True
    assert has_access({"ba"}, "pricing") is False  # commercial confidential
    assert has_access({"domain_expert"}, "domain_notes") is True
    assert has_access({"domain_expert"}, "hld") is False


def test_empty_role_set_denies() -> None:
    for key in ALL_ARTIFACT_KEYS:
        assert has_access(set(), key) is False


def test_blank_strings_ignored() -> None:
    # The header parser may feed "admin,," — empties must not leak through.
    assert has_access({"admin", "", "  "}, "triage") is True
    assert has_access({"", "  "}, "bid_card") is False


def test_every_artifact_has_admin_plus_bid_manager() -> None:
    # Guardrail: if someone removes admin or bid_manager from any row the test
    # surfaces it. These two always hold the full picture for operational
    # reasons (admin = break-glass; bid_manager = owner of the bid).
    for key, allowed in ARTIFACT_ACL.items():
        assert "admin" in allowed, f"{key!r} missing admin"
        assert "bid_manager" in allowed, f"{key!r} missing bid_manager"


def test_visible_artifacts_admin_returns_all() -> None:
    assert visible_artifacts({"admin"}) == set(ALL_ARTIFACT_KEYS)


def test_visible_artifacts_ba_only() -> None:
    # BA should see bid_card + ba_draft + scoping + wbs + retrospective — NOT
    # pricing, triage, sa_draft, etc.
    visible = visible_artifacts({"ba"})
    assert "ba_draft" in visible
    assert "scoping" in visible
    assert "wbs" in visible
    assert "retrospective" in visible
    assert "bid_card" in visible
    assert "pricing" not in visible
    assert "triage" not in visible
    assert "sa_draft" not in visible


def test_acl_as_json_is_sorted() -> None:
    payload = acl_as_json()
    assert set(payload) == set(ALL_ARTIFACT_KEYS)
    for key, roles in payload.items():
        assert roles == sorted(roles), f"{key!r} roles not sorted"
        assert set(roles) <= ALL_ROLES, f"{key!r} contains unknown role"


def test_canonical_json_matches_source() -> None:
    """Drift guard: `src/shared/acl-map.json` must match the Python source.

    When this fails, regenerate the JSON via the procedure in
    `src/shared/README.md` (also update the NestJS fallback to match).
    """
    import json
    from pathlib import Path

    repo_src = Path(__file__).resolve().parents[2]
    canonical_path = repo_src / "shared" / "acl-map.json"
    canonical = json.loads(canonical_path.read_text())
    assert acl_as_json() == canonical, (
        "ACL drift: src/shared/acl-map.json is out of sync with "
        "ai-service/workflows/acl.py. See src/shared/README.md for the "
        "update procedure."
    )
