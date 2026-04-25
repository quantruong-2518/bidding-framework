"""Unit tests for the Phase 3.7 :mod:`tools.llm` abstraction.

Covers types validation, error classification, retry semantics, cost
calculation, structured output, and the LiteLLM adapter end-to-end with
``acompletion_fn`` injected (no live HTTP).

Tests stay LLM-free — the adapter never imports ``litellm`` along the
test path because we inject ``acompletion_fn``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from tools.llm import (
    FakeLLMClient,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ScriptedResponse,
    TokenUsage,
)
from tools.llm.cost import calculate_cost_usd
from tools.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMValidationError,
    classify_provider_error,
)
from tools.llm.litellm_adapter import (
    LiteLLMClient,
    _build_sdk_messages,
    _extract_text,
    _extract_usage,
    _maybe_parse_schema,
)
from tools.llm.retry import with_retry


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal stub mirroring :class:`config.llm.LLMSettings`."""

    def __init__(
        self,
        *,
        provider: str = "anthropic",
        reasoning: str = "anthropic/claude-sonnet-4-6",
        extraction: str = "anthropic/claude-haiku-4-5",
        timeout_s: float = 30.0,
        max_retries: int = 3,
        retry_initial_wait_s: float = 0.001,
        retry_max_wait_s: float = 0.01,
    ) -> None:
        self.provider = provider
        self._reasoning = reasoning
        self._extraction = extraction
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.retry_initial_wait_s = retry_initial_wait_s
        self.retry_max_wait_s = retry_max_wait_s

    def resolved_model(self, role: str) -> str:
        return self._reasoning if role == "reasoning" else self._extraction


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = type("Msg", (), {"content": content})()
        self.finish_reason = finish_reason


class _FakeUsage:
    def __init__(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_write


class _FakeResponse:
    def __init__(
        self,
        *,
        content: str = "",
        finish_reason: str = "stop",
        usage: _FakeUsage | None = None,
    ) -> None:
        self.choices = [_FakeChoice(content, finish_reason)]
        self.usage = usage or _FakeUsage()


def _build_acompletion(responses: list[Any]):
    """Return an async fn that yields scripted responses in order."""
    iterator = iter(responses)

    async def _acompletion(**_kwargs: Any) -> Any:
        try:
            return next(iterator)
        except StopIteration as exc:
            raise AssertionError("acompletion called more times than scripted") from exc

    return _acompletion


# ---------------------------------------------------------------------------
# Type tests
# ---------------------------------------------------------------------------


def test_llm_message_validates_role() -> None:
    LLMMessage(role="user", content="hi")
    with pytest.raises(Exception):  # noqa: PT011 — Pydantic raises ValidationError
        LLMMessage(role="bot", content="hi")  # type: ignore[arg-type]


def test_llm_request_defaults() -> None:
    req = LLMRequest(messages=[LLMMessage(role="user", content="hi")])
    assert req.role == "reasoning"
    assert req.cache_policy == "ephemeral"
    assert req.max_tokens == 2048
    assert req.timeout_s == 30.0
    assert req.response_schema is None


def test_token_usage_total() -> None:
    u = TokenUsage(input_tokens=100, output_tokens=50, cache_read_tokens=200)
    assert u.total_tokens == 150  # cache reads NOT counted into total


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("RateLimitError", LLMRateLimitError),
        ("AuthenticationError", LLMAuthError),
        ("BadRequestError", LLMValidationError),
        ("APITimeoutError", LLMTimeoutError),
        ("APIConnectionError", LLMProviderError),
        ("ServiceUnavailableError", LLMProviderError),
        ("SomethingNobodyKnowsError", LLMProviderError),
    ],
)
def test_classify_provider_error_maps_known_exceptions(name: str, expected: type) -> None:
    cls = type(name, (Exception,), {})
    classified = classify_provider_error(cls("upstream message"))
    assert isinstance(classified, expected)
    assert "upstream message" in str(classified)


# ---------------------------------------------------------------------------
# Retry layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_succeeds_on_second_attempt() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMRateLimitError("429 first time")
        return "ok"

    result = await with_retry(
        flaky,
        max_attempts=3,
        initial_wait_s=0.001,
        max_wait_s=0.01,
        op_name="test",
    )
    assert result == "ok"
    assert attempts == 2


@pytest.mark.asyncio
async def test_with_retry_does_not_retry_auth_errors() -> None:
    attempts = 0

    async def hard_fail() -> str:
        nonlocal attempts
        attempts += 1
        raise LLMAuthError("401")

    with pytest.raises(LLMAuthError):
        await with_retry(
            hard_fail,
            max_attempts=3,
            initial_wait_s=0.001,
            max_wait_s=0.01,
        )
    assert attempts == 1  # auth errors fail fast


@pytest.mark.asyncio
async def test_with_retry_exhausts_and_reraises() -> None:
    async def always_fail() -> str:
        raise LLMProviderError("upstream is down")

    with pytest.raises(LLMProviderError):
        await with_retry(
            always_fail,
            max_attempts=2,
            initial_wait_s=0.001,
            max_wait_s=0.01,
        )


# ---------------------------------------------------------------------------
# Cost calculation (fallback path — litellm not installed in this env)
# ---------------------------------------------------------------------------


def test_calculate_cost_anthropic_sonnet() -> None:
    cost = calculate_cost_usd(
        model="anthropic/claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )
    # 1M input × $3 + 0.5M output × $15 = $3 + $7.50 = $10.50
    assert cost == pytest.approx(10.50, rel=1e-6)


def test_calculate_cost_openai_mini() -> None:
    cost = calculate_cost_usd(
        model="openai/gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    # 1M × $0.15 + 1M × $0.60 = $0.75
    assert cost == pytest.approx(0.75, rel=1e-6)


def test_calculate_cost_unknown_model_zero() -> None:
    cost = calculate_cost_usd(
        model="rare-vendor/foo-1",
        input_tokens=1_000,
        output_tokens=1_000,
    )
    assert cost == 0.0


def test_calculate_cost_strips_versioned_haiku_id() -> None:
    cost = calculate_cost_usd(
        model="anthropic/claude-haiku-4-5-20251001",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    # 1M input × $1 = $1
    assert cost == pytest.approx(1.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------


def test_build_sdk_messages_wraps_system_for_ephemeral_cache() -> None:
    req = LLMRequest(
        messages=[
            LLMMessage(role="system", content="long prompt"),
            LLMMessage(role="user", content="hi"),
        ],
        cache_policy="ephemeral",
    )
    sdk = _build_sdk_messages(req)
    assert sdk[0]["role"] == "system"
    assert isinstance(sdk[0]["content"], list)
    assert sdk[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # User message stays as plain string.
    assert sdk[1] == {"role": "user", "content": "hi"}


def test_build_sdk_messages_skips_cache_block_when_policy_none() -> None:
    req = LLMRequest(
        messages=[LLMMessage(role="system", content="x")],
        cache_policy="none",
    )
    sdk = _build_sdk_messages(req)
    assert sdk == [{"role": "system", "content": "x"}]


def test_extract_text_from_fake_response() -> None:
    resp = _FakeResponse(content="hello world")
    assert _extract_text(resp) == "hello world"


def test_extract_usage_normalizes_cache_fields() -> None:
    resp = _FakeResponse(
        usage=_FakeUsage(
            prompt_tokens=100,
            completion_tokens=50,
            cache_read=80,
            cache_write=20,
        )
    )
    usage = _extract_usage(resp)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.cache_read_tokens == 80
    assert usage.cache_write_tokens == 20


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


class _Sample(BaseModel):
    answer: str
    score: float


def test_maybe_parse_schema_strips_code_fence() -> None:
    raw = '```json\n{"answer": "yes", "score": 0.9}\n```'
    parsed = _maybe_parse_schema(raw, _Sample)
    assert parsed is not None
    assert parsed.answer == "yes"
    assert parsed.score == 0.9


def test_maybe_parse_schema_returns_none_on_invalid_json() -> None:
    assert _maybe_parse_schema("not json at all", _Sample) is None


def test_maybe_parse_schema_returns_none_on_validation_failure() -> None:
    # Missing `score` field
    assert _maybe_parse_schema('{"answer": "yes"}', _Sample) is None


# ---------------------------------------------------------------------------
# LiteLLMClient end-to-end (with injected acompletion_fn — no real LiteLLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_litellm_client_basic_generate() -> None:
    response_obj = _FakeResponse(
        content="hello",
        usage=_FakeUsage(prompt_tokens=12, completion_tokens=3),
    )
    acompletion = _build_acompletion([response_obj])
    client = LiteLLMClient(
        settings=_FakeSettings(),
        acompletion_fn=acompletion,
    )

    result = await client.generate(
        LLMRequest(
            messages=[
                LLMMessage(role="system", content="be brief"),
                LLMMessage(role="user", content="say hi"),
            ],
        )
    )
    assert result.text == "hello"
    assert result.provider == "anthropic"
    assert result.model == "anthropic/claude-sonnet-4-6"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 3
    assert result.cost_usd > 0


@pytest.mark.asyncio
async def test_litellm_client_role_extraction_routes_to_extraction_model() -> None:
    response_obj = _FakeResponse(content="x")
    client = LiteLLMClient(
        settings=_FakeSettings(extraction="openai/gpt-4o-mini"),
        acompletion_fn=_build_acompletion([response_obj]),
    )
    result = await client.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="x")],
            role="extraction",
        )
    )
    assert result.model == "openai/gpt-4o-mini"
    assert result.provider == "openai"


@pytest.mark.asyncio
async def test_litellm_client_classifies_rate_limit_as_retryable() -> None:
    rate_limit_cls = type("RateLimitError", (Exception,), {})

    calls = 0

    async def acompletion(**_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise rate_limit_cls("429 too many")
        return _FakeResponse(content="ok")

    client = LiteLLMClient(
        settings=_FakeSettings(max_retries=3),
        acompletion_fn=acompletion,
    )
    result = await client.generate(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")])
    )
    assert result.text == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_litellm_client_does_not_retry_auth_errors() -> None:
    auth_cls = type("AuthenticationError", (Exception,), {})
    calls = 0

    async def acompletion(**_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise auth_cls("401")

    client = LiteLLMClient(
        settings=_FakeSettings(max_retries=3),
        acompletion_fn=acompletion,
    )
    with pytest.raises(LLMAuthError):
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_litellm_client_timeout_raises_llm_timeout_error() -> None:
    async def slow_acompletion(**_kwargs: Any) -> Any:
        await asyncio.sleep(2.0)
        return _FakeResponse(content="never")

    client = LiteLLMClient(
        settings=_FakeSettings(max_retries=1),
        acompletion_fn=slow_acompletion,
    )
    with pytest.raises(LLMTimeoutError):
        await client.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="hi")],
                timeout_s=0.05,
            )
        )


@pytest.mark.asyncio
async def test_litellm_client_structured_output_happy_path() -> None:
    good_json = '{"answer": "yes", "score": 0.9}'
    client = LiteLLMClient(
        settings=_FakeSettings(),
        acompletion_fn=_build_acompletion([_FakeResponse(content=good_json)]),
    )
    result = await client.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="ask")],
            response_schema=_Sample,
        )
    )
    assert result.parsed is not None
    assert isinstance(result.parsed, _Sample)
    assert result.parsed.answer == "yes"
    assert result.parsed.score == 0.9


@pytest.mark.asyncio
async def test_litellm_client_structured_output_retries_with_error_echo() -> None:
    bad_then_good = [
        _FakeResponse(content="not even json"),
        _FakeResponse(content='{"answer": "fixed", "score": 0.5}'),
    ]
    client = LiteLLMClient(
        settings=_FakeSettings(),
        acompletion_fn=_build_acompletion(bad_then_good),
    )
    result = await client.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="ask")],
            response_schema=_Sample,
        )
    )
    assert result.parsed is not None
    assert result.parsed.answer == "fixed"


@pytest.mark.asyncio
async def test_litellm_client_structured_output_gives_up_after_one_retry() -> None:
    bad_responses = [
        _FakeResponse(content="garbage"),
        _FakeResponse(content="still garbage"),
    ]
    client = LiteLLMClient(
        settings=_FakeSettings(),
        acompletion_fn=_build_acompletion(bad_responses),
    )
    with pytest.raises(LLMValidationError):
        await client.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="ask")],
                response_schema=_Sample,
            )
        )


@pytest.mark.asyncio
async def test_litellm_client_explicit_model_overrides_settings() -> None:
    client = LiteLLMClient(
        settings=_FakeSettings(reasoning="anthropic/claude-sonnet-4-6"),
        acompletion_fn=_build_acompletion([_FakeResponse(content="ok")]),
    )
    result = await client.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            model="openai/gpt-4o",
        )
    )
    assert result.model == "openai/gpt-4o"
    assert result.provider == "openai"


# ---------------------------------------------------------------------------
# FakeLLMClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_llm_client_returns_scripted_response() -> None:
    fake = FakeLLMClient(ScriptedResponse(text="hello"))
    response = await fake.generate(
        LLMRequest(messages=[LLMMessage(role="user", content="x")])
    )
    assert response.text == "hello"
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_fake_llm_client_iterates_script_then_sticks() -> None:
    fake = FakeLLMClient(
        [
            ScriptedResponse(text="first"),
            ScriptedResponse(text="second"),
        ]
    )
    r1 = await fake.generate(LLMRequest(messages=[LLMMessage(role="user", content="x")]))
    r2 = await fake.generate(LLMRequest(messages=[LLMMessage(role="user", content="y")]))
    r3 = await fake.generate(LLMRequest(messages=[LLMMessage(role="user", content="z")]))
    assert r1.text == "first"
    assert r2.text == "second"
    # Sticky: third call replays the last script entry.
    assert r3.text == "second"


@pytest.mark.asyncio
async def test_fake_llm_client_stream_dispatches_per_word() -> None:
    fake = FakeLLMClient(ScriptedResponse(text="alpha beta gamma"))
    chunks: list[str] = []

    async def collect(token: str) -> None:
        chunks.append(token)

    response = await fake.generate_stream(
        LLMRequest(messages=[LLMMessage(role="user", content="x")]),
        on_token=collect,
    )
    assert response.text == "alpha beta gamma"
    assert "".join(chunks).strip() == "alpha beta gamma"


@pytest.mark.asyncio
async def test_fake_llm_client_raises_scripted_error() -> None:
    fake = FakeLLMClient(
        ScriptedResponse(raise_error=LLMRateLimitError("429 simulated"))
    )
    with pytest.raises(LLMRateLimitError):
        await fake.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="x")])
        )


@pytest.mark.asyncio
async def test_fake_llm_client_validates_against_schema() -> None:
    fake = FakeLLMClient(
        ScriptedResponse(text='{"answer": "ok", "score": 0.7}')
    )
    response = await fake.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="x")],
            response_schema=_Sample,
        )
    )
    assert response.parsed is not None
    assert response.parsed.answer == "ok"


def test_fake_llm_client_is_an_llm_client_subclass() -> None:
    assert issubclass(FakeLLMClient, LLMClient)


# ---------------------------------------------------------------------------
# Smoke check that the abstract class refuses direct instantiation.
# ---------------------------------------------------------------------------


def test_llm_client_abstract() -> None:
    with pytest.raises(TypeError):
        LLMClient()  # type: ignore[abstract]
