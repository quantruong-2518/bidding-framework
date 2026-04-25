"""Tests for `apply_role_filter` — the BidState scrubber called by /workflows/bid/{id}.

The router's filter logic was extracted from a FastAPI handler into a pure
function so it can be unit-tested without a Temporal client. These tests
construct a fully-populated BidState in-process, run the filter, and assert
the right fields end up scrubbed for each role profile.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from workflows.acl import ALL_ARTIFACT_KEYS
from workflows.models import BidCard, BidState


# Override conftest fixtures that pull in temporalio / Redis / kb-vault — this
# test file deals only with Pydantic models + a pure helper.
@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


@pytest.fixture(autouse=True)
def _sandbox_kb_vault(tmp_path):
    yield tmp_path


def _populated_bid_state() -> BidState:
    """Build a BidState with every artifact field non-None / non-empty.

    `model_construct` bypasses Pydantic validation so we can stuff sentinel
    `object()` values into typed fields — the role filter only reads the
    truthiness, not the schema, so this is safe for the unit under test.
    """

    bid_card = BidCard(
        client_name="ACME",
        industry="banking",
        region="APAC",
        deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
        scope_summary="core banking modernization",
        estimated_profile="M",
    )
    return BidState.model_construct(
        bid_id=uuid4(),
        current_state="S11_DONE",
        bid_card=bid_card,
        triage=object(),
        scoping=object(),
        profile="M",  # noqa: skip — BidProfile is a Literal, not an enum
        ba_draft=object(),
        sa_draft=object(),
        domain_notes=object(),
        convergence=object(),
        hld=object(),
        wbs=object(),
        pricing=object(),
        proposal_package=object(),
        reviews=[object()],
        submission=object(),
        retrospective=object(),
        loop_back_history=[],
    )


def test_admin_keeps_every_field() -> None:
    from workflows.acl import apply_role_filter

    state = _populated_bid_state()
    out = apply_role_filter(state, ["admin"])
    for key in ALL_ARTIFACT_KEYS:
        value = getattr(out, key)
        if key == "reviews":
            assert value, f"admin lost {key}"
        else:
            assert value is not None, f"admin lost {key}"


def test_empty_roles_skips_filter() -> None:
    """Internal callers omit the header — no filter applied."""
    from workflows.acl import apply_role_filter

    state = _populated_bid_state()
    out = apply_role_filter(state, [])
    assert out.pricing is not None
    assert out.triage is not None


def test_ba_loses_pricing_and_triage_and_sa() -> None:
    from workflows.acl import apply_role_filter

    state = _populated_bid_state()
    out = apply_role_filter(state, ["ba"])
    # Should keep:
    assert out.bid_card is not None
    assert out.scoping is not None
    assert out.ba_draft is not None
    assert out.wbs is not None
    assert out.retrospective is not None
    # Should scrub:
    assert out.triage is None
    assert out.pricing is None
    assert out.sa_draft is None
    assert out.domain_notes is None
    assert out.hld is None
    assert out.convergence is None
    assert out.proposal_package is None
    assert out.submission is None


def test_qc_sees_pricing_but_domain_expert_does_not() -> None:
    from workflows.acl import apply_role_filter

    qc_state = _populated_bid_state()
    de_state = _populated_bid_state()
    apply_role_filter(qc_state, ["qc"])
    apply_role_filter(de_state, ["domain_expert"])

    assert qc_state.pricing is not None
    assert qc_state.proposal_package is not None
    assert de_state.pricing is None
    assert de_state.proposal_package is None
    assert de_state.domain_notes is not None  # domain_expert keeps own field


def test_reviews_field_becomes_empty_list_not_none() -> None:
    """`reviews` is typed list[ReviewRecord]; setting None would type-error.

    The filter must reduce it to [] for users who can't see reviews.
    """
    from workflows.acl import apply_role_filter

    state = _populated_bid_state()
    out = apply_role_filter(state, ["ba"])
    # `ba` is NOT in the reviews ACL.
    assert out.reviews == []
    assert isinstance(out.reviews, list)


def test_filter_is_idempotent() -> None:
    from workflows.acl import apply_role_filter

    state = _populated_bid_state()
    apply_role_filter(state, ["ba"])
    snapshot = {k: getattr(state, k) for k in ALL_ARTIFACT_KEYS}
    apply_role_filter(state, ["ba"])
    for key, value in snapshot.items():
        assert getattr(state, key) == value or value is None


def test_multi_role_union() -> None:
    """A user with [ba, bid_manager] sees the union of both roles' artifacts."""
    from workflows.acl import apply_role_filter

    state = _populated_bid_state()
    out = apply_role_filter(state, ["ba", "bid_manager"])
    # bid_manager has access to everything, so nothing should be scrubbed.
    for key in ALL_ARTIFACT_KEYS:
        value = getattr(out, key)
        if key == "reviews":
            assert value, f"union lost {key}"
        else:
            assert value is not None, f"union lost {key}"
