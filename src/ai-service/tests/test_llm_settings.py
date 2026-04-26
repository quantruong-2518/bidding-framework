"""Phase 3.7c — env-driven provider switch coverage.

Verifies:

- :meth:`LLMSettings.resolved_model` falls back to provider defaults
  and honours explicit overrides.
- :func:`is_llm_available` checks the right env var per provider.
- :class:`tools.claude_client.ClaudeClient` (the compat wrapper) drops
  the explicit Anthropic model ID when the active provider is not
  Anthropic, so role-based routing kicks in inside the LiteLLM adapter.
"""

from __future__ import annotations

import pytest

from config.llm import (
    PROVIDER_DEFAULTS,
    PROVIDER_KEY_VARS,
    LLMSettings,
    get_llm_settings,
    is_llm_available,
)
from tools.claude_client import HAIKU, SONNET, ClaudeClient
from tools.llm import FakeLLMClient


# ---------------------------------------------------------------------------
# Settings + model resolution
# ---------------------------------------------------------------------------


def test_provider_defaults_table_lists_known_providers() -> None:
    assert set(PROVIDER_DEFAULTS) == {"anthropic", "openai", "bedrock", "gemini"}
    for provider, by_tier in PROVIDER_DEFAULTS.items():
        assert set(by_tier) == {"nano", "small", "flagship", "deep"}, provider
        for tier, model_id in by_tier.items():
            assert model_id.startswith(f"{provider}/"), (provider, tier)


def test_resolved_model_falls_back_to_provider_default() -> None:
    s = LLMSettings(provider="openai")
    assert s.resolved_model("reasoning") == "openai/gpt-4o"
    assert s.resolved_model("extraction") == "openai/gpt-4o-mini"


def test_resolved_model_honours_explicit_override() -> None:
    s = LLMSettings(
        provider="openai",
        model_reasoning="openai/o1-preview",
        model_extraction="openai/gpt-4o-mini",
    )
    assert s.resolved_model("reasoning") == "openai/o1-preview"


def test_resolved_model_partial_override() -> None:
    """User overrides extraction only; reasoning falls back to default."""
    s = LLMSettings(
        provider="openai",
        model_extraction="openai/gpt-4o-mini",
    )
    assert s.resolved_model("reasoning") == "openai/gpt-4o"
    assert s.resolved_model("extraction") == "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# is_llm_available
# ---------------------------------------------------------------------------


def test_is_llm_available_false_without_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in PROVIDER_KEY_VARS.values():
        monkeypatch.delenv(var, raising=False)
    get_llm_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert is_llm_available() is False
    get_llm_settings.cache_clear()


def test_is_llm_available_checks_anthropic_key_for_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in PROVIDER_KEY_VARS.values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic-stub")
    get_llm_settings.cache_clear()
    assert is_llm_available() is True
    get_llm_settings.cache_clear()


def test_is_llm_available_checks_openai_key_for_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in PROVIDER_KEY_VARS.values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    # Anthropic key set but provider is openai → still unavailable.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    get_llm_settings.cache_clear()
    assert is_llm_available() is False

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-stub")
    get_llm_settings.cache_clear()
    assert is_llm_available() is True
    get_llm_settings.cache_clear()


def test_is_llm_available_uses_aws_access_key_for_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in PROVIDER_KEY_VARS.values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    get_llm_settings.cache_clear()
    assert is_llm_available() is False
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-stub")
    get_llm_settings.cache_clear()
    assert is_llm_available() is True
    get_llm_settings.cache_clear()


# ---------------------------------------------------------------------------
# Provider-aware wrapper — drops explicit model on non-Anthropic provider.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrapper_keeps_explicit_model_when_provider_is_anthropic() -> None:
    fake = FakeLLMClient()
    settings = LLMSettings(provider="anthropic")
    client = ClaudeClient(llm_client=fake, settings=settings)

    await client.generate(
        model=HAIKU,
        system="s",
        messages=[{"role": "user", "content": "x"}],
    )
    req = fake.calls[0]
    assert req.model == HAIKU
    assert req.role == "extraction"


@pytest.mark.asyncio
async def test_wrapper_drops_explicit_model_when_provider_is_openai() -> None:
    """When LLM_PROVIDER=openai the legacy `model=HAIKU` arg should NOT
    pin the call to Anthropic — the wrapper drops it so the LiteLLM
    adapter resolves to gpt-4o-mini via role routing."""
    fake = FakeLLMClient()
    settings = LLMSettings(provider="openai")
    client = ClaudeClient(llm_client=fake, settings=settings)

    await client.generate(
        model=HAIKU,
        system="s",
        messages=[{"role": "user", "content": "x"}],
    )
    req = fake.calls[0]
    assert req.model is None
    assert req.role == "extraction"


@pytest.mark.asyncio
async def test_wrapper_drops_sonnet_id_on_openai_provider() -> None:
    fake = FakeLLMClient()
    settings = LLMSettings(provider="openai")
    client = ClaudeClient(llm_client=fake, settings=settings)

    await client.generate(
        model=SONNET,
        system="s",
        messages=[{"role": "user", "content": "x"}],
    )
    req = fake.calls[0]
    assert req.model is None
    assert req.role == "reasoning"


@pytest.mark.asyncio
async def test_wrapper_drops_explicit_model_on_bedrock_provider() -> None:
    fake = FakeLLMClient()
    settings = LLMSettings(provider="bedrock")
    client = ClaudeClient(llm_client=fake, settings=settings)

    await client.generate(
        model=HAIKU,
        system="s",
        messages=[{"role": "user", "content": "x"}],
    )
    assert fake.calls[0].model is None
