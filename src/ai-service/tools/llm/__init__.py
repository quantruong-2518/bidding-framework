"""Provider-agnostic LLM client for the AI service (Phase 3.7).

Public surface:

    from tools.llm import LLMClient, LLMRequest, LLMResponse, LLMMessage
    from tools.llm import get_default_client, FakeLLMClient
    from tools.llm.errors import LLMError, LLMRateLimitError, LLMTimeoutError

The concrete adapter lives in :mod:`tools.llm.litellm_adapter`. Callers should
depend only on the :class:`LLMClient` ABC so swapping the underlying SDK
(LiteLLM today, possibly Portkey or a native multi-adapter tomorrow) is a
one-file change.
"""

from __future__ import annotations

from tools.llm.client import LLMClient, get_default_client
from tools.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMValidationError,
)
from tools.llm.fake import FakeLLMClient, ScriptedResponse
from tools.llm.types import LLMMessage, LLMRequest, LLMResponse, TokenUsage

__all__ = [
    "LLMClient",
    "LLMRequest",
    "LLMResponse",
    "LLMMessage",
    "TokenUsage",
    "FakeLLMClient",
    "ScriptedResponse",
    "get_default_client",
    "LLMError",
    "LLMRateLimitError",
    "LLMAuthError",
    "LLMValidationError",
    "LLMTimeoutError",
    "LLMProviderError",
]
