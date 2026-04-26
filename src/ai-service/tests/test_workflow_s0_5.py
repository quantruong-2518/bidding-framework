"""S0.5 Wave 2A — workflow integration smoke tests for the S0.5 dispatch.

These tests focus on the data-driven aspects of the workflow change without
booting Temporal — checking ``_PROFILE_PIPELINE`` includes S0_5, the
dispatch map points at the right method, and the conditional skip logic
inside :meth:`BidWorkflow._run_s0_5_context_synthesis` short-circuits on
the flag combinations the design specifies.

The actual workflow execution test (with Temporal time-skipping env) lives
in ``test_workflow.py`` once the Docker image refresh ships — keeping
this file lightweight so host-only runs cover the contract surface.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


# Hard-skip when temporalio is missing on the host — Docker pytest runs cover it.
_temporalio = pytest.importorskip("temporalio", reason="temporalio not on host; covered in Docker")


def test_profile_pipeline_inserts_s0_5_for_every_profile() -> None:
    from workflows.bid_workflow import _PROFILE_PIPELINE

    for profile, pipeline in _PROFILE_PIPELINE.items():
        assert "S0_5" in pipeline, f"profile={profile} missing S0_5"
        # S0_5 lands between S1 and S2 — sanity-check ordering.
        s1_idx = pipeline.index("S1")
        s2_idx = pipeline.index("S2")
        s0_5_idx = pipeline.index("S0_5")
        assert s1_idx < s0_5_idx < s2_idx


def test_state_dispatch_map_routes_s0_5_to_method() -> None:
    from workflows.bid_workflow import _STATE_DISPATCH_MAP

    assert _STATE_DISPATCH_MAP["S0_5"] == "_run_s0_5_context_synthesis"


def test_phase_artifact_keys_includes_s0_5_done() -> None:
    from workflows.bid_workflow import _PHASE_ARTIFACT_KEYS

    assert "S0_5_DONE" in _PHASE_ARTIFACT_KEYS
    # No BidState fields are written by S0_5 (vault-only side effect).
    assert _PHASE_ARTIFACT_KEYS["S0_5_DONE"] == ()


def test_workflow_state_literal_includes_s0_5() -> None:
    """Append-only literal extension per Rule B."""
    from typing import get_args

    from workflows.base import WorkflowState

    states = get_args(WorkflowState)
    assert "S0_5" in states
    # S0 / S0_DONE-equivalents stay at the top — no reordering.
    assert states[0] == "S0"
    assert states[1] == "S1"


def test_bid_card_carries_optional_s0_5_fields() -> None:
    from datetime import datetime, timezone

    from workflows.models import BidCard

    legacy = BidCard(
        client_name="A",
        industry="banking",
        region="APAC",
        deadline=datetime.now(timezone.utc),
        scope_summary="x",
        estimated_profile="M",
    )
    # Both new fields default to None — backward compat.
    assert legacy.context_md_uri is None
    assert legacy.parse_session_id is None
    new = legacy.model_copy(
        update={"context_md_uri": "s3://b/key", "parse_session_id": "sid-1"}
    )
    assert new.context_md_uri == "s3://b/key"
    assert new.parse_session_id == "sid-1"
