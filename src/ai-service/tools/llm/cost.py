"""Provider-aware cost calculation.

Wraps :func:`litellm.completion_cost` so callers get USD without knowing
provider price tables. Falls back to a rough Anthropic-style estimate
when LiteLLM isn't installed (dev hosts) or the model is unknown — the
fallback is intentionally conservative so cost panels never under-report.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["calculate_cost_usd", "FALLBACK_PRICING"]


# Per-1M-token rates ($USD). Used only when LiteLLM's cost table is
# unavailable. Keep aligned with provider public pricing.
FALLBACK_PRICING: dict[str, tuple[float, float]] = {
    # input_per_1m, output_per_1m
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}


def calculate_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    provider_response: Any | None = None,
) -> float:
    """Compute USD cost for a single LLM call.

    Args:
        model: fully-qualified or short model name. The function looks up
            both — ``"anthropic/claude-sonnet-4-6"`` and ``"claude-sonnet-4-6"``
            both match the fallback table.
        input_tokens / output_tokens: token counters from the response.
        provider_response: optional raw LiteLLM ``ModelResponse``. When
            present we prefer ``litellm.completion_cost(...)`` for accurate
            provider pricing (cache discounts, regional surcharges).

    Returns:
        USD cost as float. ``0.0`` when both LiteLLM and the fallback table
        miss (caller should still log; ``0.0`` won't break dashboards).
    """
    if provider_response is not None:
        try:
            import litellm  # type: ignore[import-not-found]

            cost = litellm.completion_cost(completion_response=provider_response)
            return float(cost or 0.0)
        except Exception as exc:  # noqa: BLE001 — fall through to manual calc
            logger.debug(
                "litellm.completion_cost unavailable model=%s err=%s",
                model,
                exc,
            )

    # Fallback path — strip the LiteLLM prefix (e.g. "anthropic/") and try
    # to match the model family.
    short = model.split("/")[-1]
    pricing = FALLBACK_PRICING.get(short)
    if pricing is None:
        # Try a prefix match — covers Claude versioned IDs like
        # "claude-haiku-4-5-20251001".
        for key, prices in FALLBACK_PRICING.items():
            if short.startswith(key):
                pricing = prices
                break

    if pricing is None:
        logger.debug("cost.unknown_model model=%s", model)
        return 0.0

    input_per_1m, output_per_1m = pricing
    return round(
        (input_tokens * input_per_1m + output_tokens * output_per_1m) / 1_000_000,
        6,
    )
