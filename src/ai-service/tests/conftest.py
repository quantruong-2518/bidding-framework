"""Ensure tests can import the ai-service package root + keep LLM-free by default."""

from __future__ import annotations

import sys
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
