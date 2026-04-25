"""In-memory :class:`LLMClient` for deterministic tests.

Drop-in replacement for :class:`LiteLLMClient` — agents accept either via
their constructor. Records every call for inspection and serves scripted
responses in order.

Usage::

    fake = FakeLLMClient([
        ScriptedResponse(text='{"foo": 1}', usage=TokenUsage(input_tokens=10, output_tokens=4)),
        ScriptedResponse(text='final answer'),
    ])
    response = await fake.generate(LLMRequest(messages=[...]))
    assert fake.calls[0].messages[0].content == "..."
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Iterable

from pydantic import BaseModel

from tools.llm.client import LLMClient, OnTokenCallback
from tools.llm.errors import LLMError
from tools.llm.litellm_adapter import _maybe_parse_schema
from tools.llm.types import LLMRequest, LLMResponse, TokenUsage

__all__ = ["FakeLLMClient", "ScriptedResponse"]


@dataclass
class ScriptedResponse:
    """One scripted answer the fake client serves."""

    text: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    latency_ms: int = 0
    stop_reason: str = "stop"
    model: str = "fake/test-model"
    provider: str = "fake"
    raise_error: BaseException | None = None
    """When set, the fake raises this instead of returning a response.
    Use to test retry / error mapping; LLMError subclasses propagate as-is."""


class FakeLLMClient(LLMClient):
    """Records calls, returns scripted responses, optionally raises errors.

    Per-test fixture instantiates with a list of :class:`ScriptedResponse`
    in the order the agent will consume them. If the agent makes more
    calls than the script length, the last response is replayed (sticky)
    — handy for tests that don't care about every call.
    """

    def __init__(
        self,
        responses: Iterable[ScriptedResponse] | ScriptedResponse | None = None,
    ) -> None:
        if responses is None:
            self._script: list[ScriptedResponse] = [ScriptedResponse(text="")]
        elif isinstance(responses, ScriptedResponse):
            self._script = [responses]
        else:
            self._script = list(responses) or [ScriptedResponse(text="")]
        self.calls: list[LLMRequest] = []

    def _next(self) -> ScriptedResponse:
        # ``calls`` already includes the current request when this is invoked,
        # so the script index is len(calls) - 1, capped at the last entry
        # (sticky replay for tests that don't care about every call).
        idx = min(len(self.calls) - 1, len(self._script) - 1)
        return self._script[max(0, idx)]

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        scripted = self._next()
        if scripted.raise_error is not None:
            raise scripted.raise_error
        return self._to_response(request, scripted)

    async def generate_stream(
        self,
        request: LLMRequest,
        *,
        on_token: OnTokenCallback | None = None,
    ) -> LLMResponse:
        self.calls.append(request)
        scripted = self._next()
        if scripted.raise_error is not None:
            raise scripted.raise_error
        # Yield one chunk per word so streaming consumers exercise both the
        # delta path and the aggregated final-text path.
        if on_token is not None:
            for word in scripted.text.split():
                await on_token(word + " ")
                await asyncio.sleep(0)  # let the event loop schedule consumers
        return self._to_response(request, scripted)

    def _to_response(
        self, request: LLMRequest, scripted: ScriptedResponse
    ) -> LLMResponse:
        parsed: BaseModel | None = None
        if request.response_schema is not None:
            parsed = _maybe_parse_schema(scripted.text, request.response_schema)
        return LLMResponse(
            text=scripted.text,
            model=scripted.model,
            provider=scripted.provider,
            stop_reason=scripted.stop_reason,
            usage=scripted.usage,
            cost_usd=scripted.cost_usd,
            latency_ms=scripted.latency_ms,
            parsed=parsed,
        )

    # --- convenience helpers for tests --------------------------------- #

    def reset(self) -> None:
        self.calls.clear()

    def assert_called(self, n: int = 1) -> None:
        if len(self.calls) != n:
            raise AssertionError(
                f"FakeLLMClient expected {n} call(s), saw {len(self.calls)}"
            )

    def __repr__(self) -> str:  # pragma: no cover
        return f"FakeLLMClient(calls={len(self.calls)}, script_len={len(self._script)})"


# Re-export for convenience: tests sometimes need to construct ad-hoc errors
# in scripted responses without importing two modules.
_ = LLMError  # keep symbol reachable for `from tools.llm.fake import LLMError` style
