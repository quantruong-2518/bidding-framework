"""Provider-neutral request / response shapes for the LLM layer.

The shapes intentionally mirror OpenAI's chat-completion vocabulary (the de
facto standard LiteLLM normalizes to) but stay independent of any SDK so
callers — agents, activities, tests — never import LiteLLM directly.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "LLMMessage",
    "TokenUsage",
    "LLMRequest",
    "LLMResponse",
    "ROLE_REASONING",
    "ROLE_EXTRACTION",
]

ROLE_REASONING = "reasoning"
ROLE_EXTRACTION = "extraction"


class LLMMessage(BaseModel):
    """A single chat message. Content stays plain string; the adapter wraps
    cache-control blocks for providers that support them (Anthropic) when
    :class:`LLMRequest.cache_policy` is ``"ephemeral"``."""

    role: Literal["system", "user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    """Normalized token-usage counters. Cache fields are 0 on providers
    without prompt caching (e.g. plain OpenAI without ``prompt_caching``)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMRequest(BaseModel):
    """Adapter-agnostic LLM call.

    - ``model`` overrides the role-based default. Use a fully-qualified
      LiteLLM name (e.g. ``"anthropic/claude-sonnet-4-6"`` or
      ``"openai/gpt-4o"``). When ``None`` the client resolves it from
      :class:`LLMSettings` based on ``role``.
    - ``role`` controls model routing — ``"reasoning"`` → Sonnet/GPT-4o,
      ``"extraction"`` → Haiku/GPT-4o-mini. Cheap default lets agents
      declare intent without hard-coding model strings.
    - ``cache_policy="ephemeral"`` requests prompt caching on the system
      message. Anthropic gets explicit ``cache_control`` blocks; OpenAI
      relies on its automatic 5-minute cache window. Either way, callers
      see the same API.
    - ``response_schema``: when set, the adapter requests JSON output and
      validates the result against the Pydantic model. On parse / validation
      failure the adapter retries once with the error fed back into the
      prompt. The validated model lands in :attr:`LLMResponse.parsed`.
    """

    messages: list[LLMMessage]
    role: Literal["reasoning", "extraction"] = "reasoning"
    model: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.3
    cache_policy: Literal["ephemeral", "none"] = "ephemeral"
    response_schema: type[BaseModel] | None = None
    timeout_s: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Optional Langfuse linkage. Caller passes the trace_id (= bid_id) and a
    # human-readable node name; the adapter forwards them to the tracer.
    trace_id: str | None = None
    node_name: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class LLMResponse(BaseModel):
    """Normalized completion result.

    - ``cost_usd`` is provider-aware: comes from
      ``litellm.completion_cost(...)`` for the LiteLLM adapter.
      Always ``0.0`` on the fake client.
    - ``parsed`` populates only when the request supplied a
      ``response_schema`` and the adapter validated successfully.
    """

    text: str
    model: str
    provider: str
    stop_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    latency_ms: int = 0
    parsed: BaseModel | None = None

    model_config = {"arbitrary_types_allowed": True}
