"""Ensure tests can import the ai-service package root + keep LLM-free by default."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _force_llm_fallback_by_default(request, monkeypatch):
    """Default tests must not call Anthropic. Only `@pytest.mark.integration` opts in.

    The S3 activity wrappers (`ba_analysis_activity`, etc.) gate on
    `get_claude_settings().api_key`. Without this fixture a dev with the key
    exported locally would trigger real LLM calls from the workflow tests.
    """
    if "integration" in request.keywords:
        yield
        return

    from config.claude import get_claude_settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_claude_settings.cache_clear()
    try:
        yield
    finally:
        get_claude_settings.cache_clear()


@pytest.fixture(autouse=True)
def _compress_gate_timeouts(request, monkeypatch):
    """Shrink workflow timeouts to seconds so time-skipping envs settle fast.

    Integration tests opt out via `@pytest.mark.integration`. Non-integration
    tests benefit from tiny timeouts since Temporal's test env uses virtual
    time — a 72h gate fires instantly under `env.start_time_skipping`.
    """
    if "integration" in request.keywords:
        yield
        return

    from workflows import bid_workflow as bwf

    fast = timedelta(seconds=5)
    monkeypatch.setattr(bwf, "HUMAN_GATE_TIMEOUT", fast, raising=False)
    monkeypatch.setattr(bwf, "ACTIVITY_TIMEOUT", fast, raising=False)
    monkeypatch.setattr(bwf, "S3_ACTIVITY_TIMEOUT", fast, raising=False)
    if hasattr(bwf, "_S9_TIMEOUT"):
        monkeypatch.setattr(
            bwf,
            "_S9_TIMEOUT",
            {p: fast for p in ("S", "M", "L", "XL")},
            raising=False,
        )
    yield


class _RedisCapture:
    """Drop-in replacement for aioredis client — records publishes in-memory."""

    def __init__(self) -> None:
        import json as _json

        self._json = _json
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel: str, message: str) -> int:
        try:
            payload = self._json.loads(message)
        except Exception:  # noqa: BLE001
            payload = {"raw": message}
        self.published.append((channel, payload))
        return 1

    async def aclose(self) -> None:
        pass

    def events_of_type(self, event_type: str) -> list[dict]:
        return [p for _, p in self.published if p.get("type") == event_type]


@pytest.fixture(autouse=True)
def _stub_redis_publish(request, monkeypatch):
    """Redirect aioredis.from_url across all publishers to an in-memory capture.

    Integration tests hit real Redis + external services; they opt out. Unit
    tests inspect `_stub_redis_publish.published` to assert bid.event contracts.
    """
    if "integration" in request.keywords:
        yield None
        return

    capture = _RedisCapture()

    def _from_url(*_args, **_kwargs):
        return capture

    for module_path in (
        "activities.notify",
        "activities.state_transition",
        "agents.stream_publisher",
    ):
        monkeypatch.setattr(f"{module_path}.aioredis.from_url", _from_url, raising=False)
    yield capture


@pytest.fixture(autouse=True)
def _sandbox_kb_vault(tmp_path, monkeypatch):
    """Redirect per-bid vault writes into pytest's tmp_path so workflow tests stay hermetic.

    The `workspace_snapshot_activity` falls back to `KB_VAULT_PATH` when the
    workflow passes an empty `vault_root`; we point that env var at a fresh
    tmp dir per test and clear the ingestion-settings cache so the activity
    re-reads it.
    """
    from config.ingestion import get_ingestion_settings

    sandbox = tmp_path / "kb-vault-sandbox"
    sandbox.mkdir(exist_ok=True)
    monkeypatch.setenv("KB_VAULT_PATH", str(sandbox))
    get_ingestion_settings.cache_clear()
    try:
        yield sandbox
    finally:
        get_ingestion_settings.cache_clear()
