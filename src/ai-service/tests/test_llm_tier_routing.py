"""Phase 3.7d — 4-tier model routing + deep-tier reasoning kwargs."""

from __future__ import annotations

import pytest

from config.llm import PROVIDER_DEFAULTS, LLMSettings
from tools.llm import FakeLLMClient, LLMMessage, LLMRequest
from tools.llm.litellm_adapter import LiteLLMClient, _deep_tier_kwargs


# ---------------------------------------------------------------------------
# Per-tier model resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["anthropic", "openai", "bedrock", "gemini"])
@pytest.mark.parametrize("tier", ["nano", "small", "flagship", "deep"])
def test_resolved_model_for_tier_falls_back_to_provider_default(
    provider: str, tier: str
) -> None:
    s = LLMSettings(provider=provider)  # type: ignore[arg-type]
    assert s.resolved_model_for_tier(tier) == PROVIDER_DEFAULTS[provider][tier]  # type: ignore[index]


def test_resolved_model_for_tier_honours_per_tier_override() -> None:
    s = LLMSettings(
        provider="openai",
        model_nano="openai/gpt-4o-mini",
        model_flagship="openai/gpt-4o",
        model_deep="openai/o3",
    )
    assert s.resolved_model_for_tier("deep") == "openai/o3"
    assert s.resolved_model_for_tier("flagship") == "openai/gpt-4o"


def test_resolved_model_for_tier_legacy_role_env_still_honoured() -> None:
    """Pre-3.7d deployments pinning LLM_MODEL_REASONING / _EXTRACTION still
    resolve correctly via the role-to-tier alias."""
    s = LLMSettings(
        provider="anthropic",
        model_reasoning="anthropic/claude-sonnet-4-6",
        model_extraction="anthropic/claude-haiku-4-5-20251001",
    )
    assert s.resolved_model_for_tier("flagship") == "anthropic/claude-sonnet-4-6"
    assert s.resolved_model_for_tier("nano") == "anthropic/claude-haiku-4-5-20251001"


def test_per_tier_env_wins_over_legacy_role_env() -> None:
    s = LLMSettings(
        provider="openai",
        model_flagship="openai/gpt-4o",
        model_reasoning="openai/o1",  # legacy — should be ignored
    )
    assert s.resolved_model_for_tier("flagship") == "openai/gpt-4o"


def test_legacy_resolved_model_shim_routes_through_tier() -> None:
    s = LLMSettings(provider="openai")
    assert s.resolved_model("reasoning") == PROVIDER_DEFAULTS["openai"]["flagship"]
    assert s.resolved_model("extraction") == PROVIDER_DEFAULTS["openai"]["nano"]


# ---------------------------------------------------------------------------
# Role → tier alias on LLMRequest
# ---------------------------------------------------------------------------


def test_request_role_extraction_aliases_to_nano_tier() -> None:
    req = LLMRequest(messages=[LLMMessage(role="user", content="x")], role="extraction")
    assert req.tier == "nano"


def test_request_role_reasoning_aliases_to_flagship_tier() -> None:
    req = LLMRequest(messages=[LLMMessage(role="user", content="x")], role="reasoning")
    assert req.tier == "flagship"


def test_explicit_tier_wins_over_role() -> None:
    req = LLMRequest(
        messages=[LLMMessage(role="user", content="x")],
        tier="deep",
        role="extraction",  # contradiction — tier wins
    )
    assert req.tier == "deep"


def test_default_tier_is_flagship() -> None:
    req = LLMRequest(messages=[LLMMessage(role="user", content="x")])
    assert req.tier == "flagship"
    assert req.role is None


# ---------------------------------------------------------------------------
# Deep-tier reasoning kwargs (provider detection by model substring)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    ["openai/o1", "openai/o1-mini", "openai/o3", "openai/o3-mini"],
)
def test_deep_tier_kwargs_for_openai_o_series(model: str) -> None:
    kwargs = _deep_tier_kwargs(model)
    assert kwargs == {"reasoning_effort": "high"}


@pytest.mark.parametrize(
    "model",
    [
        "anthropic/claude-opus-4-7",
        "anthropic/claude-3-opus-20240229",
        "bedrock/anthropic.claude-3-opus-20240229-v1:0",
    ],
)
def test_deep_tier_kwargs_for_anthropic_opus(model: str) -> None:
    kwargs = _deep_tier_kwargs(model)
    assert kwargs == {"thinking": {"type": "enabled", "budget_tokens": 8000}}


@pytest.mark.parametrize(
    "model",
    ["gemini/gemini-1.5-pro", "openai/gpt-4o", "anthropic/claude-sonnet-4-6"],
)
def test_deep_tier_kwargs_empty_for_non_reasoning_models(model: str) -> None:
    assert _deep_tier_kwargs(model) == {}


# ---------------------------------------------------------------------------
# LiteLLMClient end-to-end — kwargs forwarded to acompletion when tier=deep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_litellm_adapter_attaches_reasoning_effort_for_deep_openai() -> None:
    captured: dict[str, object] = {}

    class _FakeResp:
        choices = [
            type("C", (), {"message": type("M", (), {"content": "ok"})(), "finish_reason": "stop"})()
        ]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()

    async def _fake_acompletion(**kwargs: object) -> _FakeResp:
        captured.update(kwargs)
        return _FakeResp()

    settings = LLMSettings(provider="openai")
    client = LiteLLMClient(settings=settings, acompletion_fn=_fake_acompletion)
    request = LLMRequest(
        messages=[LLMMessage(role="user", content="hi")],
        tier="deep",
    )
    response = await client.generate(request)
    assert captured["model"] == "openai/o1"
    assert captured["reasoning_effort"] == "high"
    assert response.text == "ok"


@pytest.mark.asyncio
async def test_litellm_adapter_attaches_thinking_for_deep_anthropic() -> None:
    captured: dict[str, object] = {}

    class _FakeResp:
        choices = [
            type("C", (), {"message": type("M", (), {"content": "ok"})(), "finish_reason": "stop"})()
        ]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()

    async def _fake_acompletion(**kwargs: object) -> _FakeResp:
        captured.update(kwargs)
        return _FakeResp()

    settings = LLMSettings(provider="anthropic")
    client = LiteLLMClient(settings=settings, acompletion_fn=_fake_acompletion)
    request = LLMRequest(
        messages=[LLMMessage(role="user", content="hi")],
        tier="deep",
    )
    await client.generate(request)
    assert captured["model"] == "anthropic/claude-opus-4-7"
    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 8000}


@pytest.mark.asyncio
async def test_litellm_adapter_no_reasoning_kwargs_for_non_deep_tiers() -> None:
    captured: dict[str, object] = {}

    class _FakeResp:
        choices = [
            type("C", (), {"message": type("M", (), {"content": "ok"})(), "finish_reason": "stop"})()
        ]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()

    async def _fake_acompletion(**kwargs: object) -> _FakeResp:
        captured.update(kwargs)
        return _FakeResp()

    settings = LLMSettings(provider="openai")
    client = LiteLLMClient(settings=settings, acompletion_fn=_fake_acompletion)

    for tier in ("nano", "small", "flagship"):
        captured.clear()
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="x")], tier=tier)  # type: ignore[arg-type]
        )
        assert "reasoning_effort" not in captured, tier
        assert "thinking" not in captured, tier


@pytest.mark.asyncio
async def test_litellm_adapter_routes_per_tier_default_when_request_model_is_none() -> None:
    captured: dict[str, object] = {}

    class _FakeResp:
        choices = [
            type("C", (), {"message": type("M", (), {"content": "ok"})(), "finish_reason": "stop"})()
        ]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()

    async def _fake_acompletion(**kwargs: object) -> _FakeResp:
        captured.update(kwargs)
        return _FakeResp()

    settings = LLMSettings(provider="openai")
    client = LiteLLMClient(settings=settings, acompletion_fn=_fake_acompletion)

    expected = {
        "nano": "openai/gpt-4o-mini",
        "small": "openai/gpt-4o-mini",
        "flagship": "openai/gpt-4o",
        "deep": "openai/o1",
    }
    for tier, expected_model in expected.items():
        captured.clear()
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="x")], tier=tier)  # type: ignore[arg-type]
        )
        assert captured["model"] == expected_model, tier


# ---------------------------------------------------------------------------
# FakeLLMClient still records the tier so conversation tests can inspect it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_client_records_tier_from_request() -> None:
    fake = FakeLLMClient()
    await fake.generate(LLMRequest(messages=[LLMMessage(role="user", content="x")], tier="deep"))
    await fake.generate(LLMRequest(messages=[LLMMessage(role="user", content="y")], tier="nano"))
    assert [c.tier for c in fake.calls] == ["deep", "nano"]
