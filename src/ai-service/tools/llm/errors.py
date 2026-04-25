"""Provider-neutral error taxonomy.

Maps the underlying SDK exceptions (LiteLLM mirrors OpenAI's hierarchy +
provider-specific variants) into a small flat set callers can branch on
without importing the vendor SDK.

Activity wrappers should treat:

  - :class:`LLMRateLimitError` as RETRYABLE — Temporal will back off.
  - :class:`LLMTimeoutError` as RETRYABLE — same.
  - :class:`LLMAuthError` / :class:`LLMValidationError` as NON-RETRYABLE —
    re-raise as ``ApplicationError(non_retryable=True)``.
  - :class:`LLMProviderError` (catch-all 5xx/unknown) as RETRYABLE.
"""

from __future__ import annotations

__all__ = [
    "LLMError",
    "LLMRateLimitError",
    "LLMAuthError",
    "LLMValidationError",
    "LLMTimeoutError",
    "LLMProviderError",
    "classify_provider_error",
]


class LLMError(Exception):
    """Base class for every error surfaced by the LLM client."""


class LLMRateLimitError(LLMError):
    """HTTP 429 / quota exceeded. Retry with backoff."""


class LLMAuthError(LLMError):
    """HTTP 401 / 403 — invalid or missing API key. Do not retry."""


class LLMValidationError(LLMError):
    """HTTP 400 — request shape rejected (bad model name, oversize prompt,
    invalid JSON-mode schema). Do not retry — the call won't succeed."""


class LLMTimeoutError(LLMError):
    """asyncio.TimeoutError or upstream timeout. Retry within budget."""


class LLMProviderError(LLMError):
    """5xx / unknown error. Retry within budget."""


def classify_provider_error(exc: BaseException) -> LLMError:
    """Map a raw SDK exception to one of the LLM error classes.

    LiteLLM exceptions live under ``litellm.exceptions``. We import lazily
    so this module stays importable without the dependency installed
    (e.g. on the dev host before ``poetry install``).
    """
    cls_name = type(exc).__name__
    msg = str(exc)

    # Order matters — RateLimitError subclasses APIError in some SDKs.
    if cls_name in {"RateLimitError", "Throttled"} or "rate_limit" in msg.lower():
        return LLMRateLimitError(msg)
    if cls_name in {"AuthenticationError", "PermissionDeniedError"} or "auth" in msg.lower():
        return LLMAuthError(msg)
    if cls_name in {"BadRequestError", "InvalidRequestError", "UnprocessableEntityError"}:
        return LLMValidationError(msg)
    if cls_name in {"APITimeoutError", "Timeout", "TimeoutError"}:
        return LLMTimeoutError(msg)
    if cls_name in {"APIConnectionError", "ServiceUnavailableError", "InternalServerError", "APIError"}:
        return LLMProviderError(msg)
    # Default — treat as provider error (retryable). The class name string
    # is preserved in the message so logs aren't lossy.
    return LLMProviderError(f"{cls_name}: {msg}")
