"""Tenacity-backed retry decorator for LLM calls.

Retries only on transient failures: rate limits, timeouts, 5xx. Does NOT
retry auth or validation errors — those won't succeed on retry, only
burn quota. Layered ABOVE Temporal's activity retry to keep the in-flight
attempt fast; activity-level retry only kicks in if all layered attempts
fail.

Defaults: 3 attempts, exponential backoff 1 → 4 → 16 s, ±20% jitter.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from tools.llm.errors import (
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

__all__ = ["with_retry", "RETRYABLE_ERRORS"]

# Errors that signal a transient upstream condition. Auth / validation are
# excluded — they're permanent for the lifetime of the request.
RETRYABLE_ERRORS = (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMProviderError,
)


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    initial_wait_s: float = 1.0,
    max_wait_s: float = 16.0,
    op_name: str = "llm_call",
) -> T:
    """Run ``func`` with retry on :data:`RETRYABLE_ERRORS`.

    Args:
        func: zero-arg async callable. Wrap closures rather than passing args
              so retries see the same input.
        max_attempts: total attempts including the first call. ``3`` means
              first try + up to 2 retries.
        initial_wait_s: starting back-off delay; doubles per attempt up to
              ``max_wait_s``.
        max_wait_s: cap on the back-off delay.
        op_name: human-readable label for log lines.

    Re-raises:
        :class:`LLMError`: the last error if every attempt failed. Always a
        subclass of LLMError because the adapter pre-classifies upstream
        exceptions in :func:`classify_provider_error`.
    """
    attempt = 0
    try:
        async for tentative in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_random_exponential(
                multiplier=initial_wait_s,
                max=max_wait_s,
            ),
            retry=retry_if_exception_type(RETRYABLE_ERRORS),
            reraise=True,
        ):
            attempt += 1
            with tentative:
                return await func()
    except LLMError as exc:
        logger.warning(
            "%s.retry_exhausted attempts=%d err=%s",
            op_name,
            attempt,
            exc,
        )
        raise
    except RetryError as exc:  # pragma: no cover — reraise=True keeps this branch dead
        underlying = exc.last_attempt.exception() if exc.last_attempt else exc
        logger.warning("%s.retry_unexpected err=%s", op_name, underlying)
        raise underlying if isinstance(underlying, BaseException) else exc

    # AsyncRetrying always raises or returns; this is unreachable but keeps
    # the type-checker happy.
    raise RuntimeError(f"{op_name}.retry exited without result")  # pragma: no cover


def with_retry_kwargs(*, max_attempts: int = 3, initial_wait_s: float = 1.0, max_wait_s: float = 16.0) -> dict[str, Any]:
    """Bundle retry knobs for easy DI / testing override."""
    return {
        "max_attempts": max_attempts,
        "initial_wait_s": initial_wait_s,
        "max_wait_s": max_wait_s,
    }
