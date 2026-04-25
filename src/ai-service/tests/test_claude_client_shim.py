"""Verify the Phase 3.7 :mod:`tools.claude_client` shim still translates
the legacy ``(model, system, messages)`` call shape correctly.

The full LiteLLM/Langfuse/structured-output coverage lives in
``tests/test_llm_client.py``; this file just confirms the *wrapper* does
its job — the BA/SA/Domain agents continue to import this module so
breaking the wrapper would silently break Phase 2.2 contracts.
"""

from __future__ import annotations

from typing import Any

import pytest

from tools.claude_client import HAIKU, SONNET, ClaudeClient, ClaudeResponse
from tools.llm import FakeLLMClient, ScriptedResponse
from tools.llm.types import LLMRequest, TokenUsage


def _make_shim(scripted: ScriptedResponse | None = None) -> tuple[ClaudeClient, FakeLLMClient]:
    fake = FakeLLMClient(scripted or ScriptedResponse(text="ok"))
    return ClaudeClient(llm_client=fake), fake


@pytest.mark.asyncio
async def test_shim_generate_translates_to_llm_request() -> None:
    client, fake = _make_shim(ScriptedResponse(text="hello"))

    response = await client.generate(
        model=HAIKU,
        system="static system prompt",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert isinstance(response, ClaudeResponse)
    assert response.text == "hello"

    # FakeLLMClient captured the translated request.
    assert len(fake.calls) == 1
    req: LLMRequest = fake.calls[0]
    # System message wraps as the first LLMMessage with role=system.
    assert req.messages[0].role == "system"
    assert req.messages[0].content == "static system prompt"
    assert req.messages[1].role == "user"
    assert req.messages[1].content == "hi"
    # ``model=HAIKU`` flows through; role inferred as extraction.
    assert req.model == HAIKU
    assert req.role == "extraction"
    assert req.cache_policy == "ephemeral"


@pytest.mark.asyncio
async def test_shim_passes_cache_policy_none_when_cache_disabled() -> None:
    client, fake = _make_shim()
    await client.generate(
        model=SONNET,
        system="plain",
        messages=[{"role": "user", "content": "hi"}],
        cache_system=False,
    )
    assert fake.calls[0].cache_policy == "none"


@pytest.mark.asyncio
async def test_shim_routes_sonnet_to_reasoning_role() -> None:
    client, fake = _make_shim()
    await client.generate(
        model=SONNET,
        system="x",
        messages=[{"role": "user", "content": "y"}],
    )
    assert fake.calls[0].role == "reasoning"


@pytest.mark.asyncio
async def test_shim_translates_usage_to_anthropic_dict_keys() -> None:
    client, _ = _make_shim(
        ScriptedResponse(
            text="answer",
            usage=TokenUsage(
                input_tokens=12,
                output_tokens=34,
                cache_read_tokens=200,
                cache_write_tokens=100,
            ),
        )
    )

    response = await client.generate(
        model=HAIKU,
        system="s",
        messages=[{"role": "user", "content": "q"}],
    )
    # Legacy callers index usage by Anthropic SDK key names.
    assert response.usage["input_tokens"] == 12
    assert response.usage["output_tokens"] == 34
    assert response.usage["cache_read_input_tokens"] == 200
    assert response.usage["cache_creation_input_tokens"] == 100


@pytest.mark.asyncio
async def test_shim_generate_stream_forwards_tokens() -> None:
    client, fake = _make_shim(ScriptedResponse(text="hello world"))

    collected: list[str] = []

    async def on_token(t: str) -> None:
        collected.append(t)

    response = await client.generate_stream(
        model=SONNET,
        system="s",
        messages=[{"role": "user", "content": "q"}],
        on_token=on_token,
    )
    assert response.text == "hello world"
    # FakeLLMClient streams one chunk per word.
    assert "".join(collected).strip() == "hello world"
    assert fake.calls[0].role == "reasoning"


@pytest.mark.asyncio
async def test_shim_passes_node_name_and_trace_id() -> None:
    client, fake = _make_shim()
    await client.generate(
        model=HAIKU,
        system="s",
        messages=[{"role": "user", "content": "q"}],
        node_name="extract_requirements",
        trace_id="bid-99",
    )
    req = fake.calls[0]
    assert req.node_name == "extract_requirements"
    assert req.trace_id == "bid-99"


@pytest.mark.asyncio
async def test_shim_warns_on_legacy_client_kwarg(caplog: pytest.LogCaptureFixture) -> None:
    """The pre-3.7 ``client=AsyncAnthropic(...)`` kwarg is no longer
    honoured — the wrapper logs a warning so callers migrate."""
    import logging

    with caplog.at_level(logging.WARNING):
        client = ClaudeClient(client=object())  # type: ignore[arg-type]
        # Construction succeeds; warning is emitted.
        assert any("ignored after Phase 3.7" in rec.message for rec in caplog.records)
        del client
