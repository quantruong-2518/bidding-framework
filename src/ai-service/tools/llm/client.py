"""LLMClient ABC + lazy default-instance accessor."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Awaitable, Callable

from tools.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "OnTokenCallback", "get_default_client", "set_default_client"]

OnTokenCallback = Callable[[str], Awaitable[None]]


class LLMClient(ABC):
    """Provider-agnostic LLM contract.

    Two methods, one shape — adapters (LiteLLM today, possibly Portkey or a
    custom HTTP client tomorrow) implement both. Agents depend on this
    interface; the concrete adapter is selected by
    :func:`get_default_client` (production) or injected directly (tests
    use :class:`tools.llm.fake.FakeLLMClient`).
    """

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Single-shot completion. Caller awaits the full response."""
        raise NotImplementedError

    @abstractmethod
    async def generate_stream(
        self,
        request: LLMRequest,
        *,
        on_token: OnTokenCallback | None = None,
    ) -> LLMResponse:
        """Stream tokens to ``on_token`` as they arrive.

        The aggregated text + final usage land in the returned
        :class:`LLMResponse` so callers can still parse JSON post-stream
        (BA/SA/Domain agents rely on this).
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Default-instance accessor.
#
# Production code calls ``get_default_client()`` to pick up the configured
# adapter without knowing whether it's LiteLLM, Fake, or a future variant.
# Tests inject a FakeLLMClient via ``set_default_client(...)`` in a fixture.
# ---------------------------------------------------------------------------

_DEFAULT_CLIENT: LLMClient | None = None


def get_default_client() -> LLMClient:
    """Return the process-wide LLM client, instantiating on first call.

    Build order:
    1. Whatever was injected via :func:`set_default_client`.
    2. :class:`tools.llm.litellm_adapter.LiteLLMClient` (the production path).

    Importing the LiteLLM adapter is deferred so unit tests that only need
    the ABC don't drag the SDK in.
    """
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is not None:
        return _DEFAULT_CLIENT
    from tools.llm.litellm_adapter import LiteLLMClient

    _DEFAULT_CLIENT = LiteLLMClient()
    return _DEFAULT_CLIENT


def set_default_client(client: LLMClient | None) -> None:
    """Override the default-client singleton. ``None`` clears it.

    Tests use this in fixtures to swap in :class:`FakeLLMClient`. Production
    code should NOT call this — adapter selection belongs in
    :class:`tools.llm.litellm_adapter.LiteLLMClient` via
    :class:`config.llm.LLMSettings`.
    """
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = client
