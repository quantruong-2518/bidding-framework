"""LLM provider + model selection (Phase 3.7 + 3.7d).

Canonical LLM configuration. :mod:`config.claude` stays as a compat
shim that re-exports ``HAIKU`` / ``SONNET`` constants and a thin
``ClaudeSettings.api_key`` property which still proxies
``ANTHROPIC_API_KEY``; activity-level "is the LLM available?" checks
should call :func:`is_llm_available` here instead so they're
provider-aware.

Environment::

    LLM_PROVIDER=anthropic           # anthropic | openai | bedrock | gemini

    # Per-tier overrides (full LiteLLM model IDs); fall back to provider defaults.
    LLM_MODEL_NANO=...               # cheap classification / extraction
    LLM_MODEL_SMALL=...              # mid utility (defaults to NANO when unset)
    LLM_MODEL_FLAGSHIP=...           # default reasoning / synthesis
    LLM_MODEL_DEEP=...               # extended thinking / o-series

    # Legacy 2-role overrides (still honoured for backward compat).
    # extraction → nano, reasoning → flagship.
    LLM_MODEL_REASONING=...
    LLM_MODEL_EXTRACTION=...

    LLM_TIMEOUT_S=30
    LLM_MAX_RETRIES=3
    LLM_RETRY_INITIAL_WAIT_S=1
    LLM_RETRY_MAX_WAIT_S=16

Per-provider API keys are read by LiteLLM from its own conventional env
vars (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``AWS_ACCESS_KEY_ID``,
``GOOGLE_API_KEY``). :func:`is_llm_available` checks the env var that
matches :attr:`LLMSettings.provider`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from tools.llm.types import LLMTier, ROLE_TO_TIER

__all__ = [
    "LLMSettings",
    "LLMProvider",
    "PROVIDER_DEFAULTS",
    "PROVIDER_KEY_VARS",
    "DEEP_TIER_KWARGS",
    "get_llm_settings",
    "is_llm_available",
]

LLMProvider = Literal["anthropic", "openai", "bedrock", "gemini"]

# 4-tier model table per provider. The user can override any tier via
# ``LLM_MODEL_<TIER>``; unset tiers fall back to this table.
#
# Tier semantics:
# - ``nano``     — cheapest; classification, extraction, JSON shaping.
# - ``small``    — mid utility; defaults to the nano model on providers
#                  without a distinct mid-tier (Anthropic, OpenAI).
# - ``flagship`` — default reasoning / synthesis.
# - ``deep``     — extended thinking; provider-specific reasoning kwargs
#                  attached by :data:`DEEP_TIER_KWARGS` lookup at call time.
PROVIDER_DEFAULTS: dict[str, dict[LLMTier, str]] = {
    "anthropic": {
        "nano": "anthropic/claude-haiku-4-5-20251001",
        "small": "anthropic/claude-haiku-4-5-20251001",
        "flagship": "anthropic/claude-sonnet-4-6",
        "deep": "anthropic/claude-opus-4-7",
    },
    "openai": {
        "nano": "openai/gpt-4o-mini",
        "small": "openai/gpt-4o-mini",
        "flagship": "openai/gpt-4o",
        # o1 is the established premium reasoning model. Override with
        # LLM_MODEL_DEEP=openai/o3 (or similar) when a newer one ships.
        "deep": "openai/o1",
    },
    "bedrock": {
        "nano": "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        "small": "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        "flagship": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "deep": "bedrock/anthropic.claude-3-opus-20240229-v1:0",
    },
    "gemini": {
        "nano": "gemini/gemini-1.5-flash",
        "small": "gemini/gemini-1.5-flash",
        "flagship": "gemini/gemini-1.5-pro",
        # Gemini's thinking mode is still evolving — default deep to
        # 1.5-pro; user can switch to gemini-2.0-flash-thinking-exp.
        "deep": "gemini/gemini-1.5-pro",
    },
}

# Env var that holds the API key per provider. LiteLLM reads these
# directly; we read them here only to gate the activity-level
# "fall back to stub" decision when no key is configured for the
# active provider. AWS uses access-key auth, so we check
# ``AWS_ACCESS_KEY_ID`` (sufficient signal — Bedrock will surface a
# more specific error at call time if the secret/role is missing).
PROVIDER_KEY_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "gemini": "GOOGLE_API_KEY",
}


def _deep_kwargs_for_o_series() -> dict[str, object]:
    """OpenAI o1 / o3 reasoning kwargs. ``high`` effort = max latency, max quality.
    Override per-call by setting ``LLMRequest.metadata['reasoning_effort']`` later
    if a finer knob is needed."""
    return {"reasoning_effort": "high"}


def _deep_kwargs_for_anthropic_thinking() -> dict[str, object]:
    """Anthropic extended thinking. 8k budget = ~$0.30 extra per call on Opus —
    high enough to chain ~3-4 reasoning steps. Override via env if cost gates."""
    return {"thinking": {"type": "enabled", "budget_tokens": 8000}}


# Provider-specific reasoning kwargs attached when ``tier == "deep"``.
# Empty dict on providers without a uniform thinking API (Gemini, Bedrock
# routes vary). Detection is by model-string substring inside
# :func:`tools.llm.litellm_adapter._deep_tier_kwargs`.
DEEP_TIER_KWARGS: dict[str, dict[str, object]] = {
    "openai_o_series": _deep_kwargs_for_o_series(),
    "anthropic_opus": _deep_kwargs_for_anthropic_thinking(),
}


class LLMSettings(BaseSettings):
    """Process-wide LLM config. Read once via :func:`get_llm_settings`."""

    model_config = SettingsConfigDict(env_prefix="LLM_", case_sensitive=False)

    provider: LLMProvider = "anthropic"

    # Per-tier overrides. Unset → fall back to PROVIDER_DEFAULTS[provider][tier].
    model_nano: str | None = None
    model_small: str | None = None
    model_flagship: str | None = None
    model_deep: str | None = None

    # Legacy 2-role overrides — still consumed by resolved_model() so
    # existing deployments pinning LLM_MODEL_REASONING continue to work.
    # When both LLM_MODEL_FLAGSHIP and LLM_MODEL_REASONING are set, the
    # tier-named one wins (it's the new canonical name).
    model_reasoning: str | None = None
    model_extraction: str | None = None

    timeout_s: float = 30.0
    max_retries: int = 3
    retry_initial_wait_s: float = 1.0
    retry_max_wait_s: float = 16.0

    def resolved_model_for_tier(self, tier: LLMTier) -> str:
        """Pick the LiteLLM model ID for a tier.

        Order:
        1. Explicit per-tier env (``LLM_MODEL_NANO`` / ``_SMALL`` / ``_FLAGSHIP`` / ``_DEEP``).
        2. Legacy ``LLM_MODEL_REASONING`` / ``_EXTRACTION`` when the tier
           maps onto the legacy role (flagship ↔ reasoning, nano ↔ extraction).
        3. Provider default from :data:`PROVIDER_DEFAULTS`.
        """
        per_tier_field = f"model_{tier}"
        explicit = getattr(self, per_tier_field, None)
        if explicit:
            return explicit

        # Legacy fallback for the two tiers that used to be roles.
        if tier == "flagship" and self.model_reasoning:
            return self.model_reasoning
        if tier == "nano" and self.model_extraction:
            return self.model_extraction

        return PROVIDER_DEFAULTS[self.provider][tier]

    def resolved_model(self, role: Literal["reasoning", "extraction"]) -> str:
        """Backward-compat shim — translate the legacy role into a tier."""
        return self.resolved_model_for_tier(ROLE_TO_TIER[role])


@lru_cache(maxsize=1)
def get_llm_settings() -> LLMSettings:
    """Process-wide LLM settings singleton."""
    return LLMSettings()


def is_llm_available() -> bool:
    """True when the configured provider has a credential set.

    Activity wrappers gate the real LLM path on this — when ``False``
    they fall back to the deterministic stubs (Phase 2.1 behaviour).
    A non-default provider (e.g. ``LLM_PROVIDER=openai``) requires
    ``OPENAI_API_KEY`` for the gate to open; ``ANTHROPIC_API_KEY`` is
    no longer the universal signal.
    """
    settings = get_llm_settings()
    var = PROVIDER_KEY_VARS.get(settings.provider, "ANTHROPIC_API_KEY")
    return bool(os.environ.get(var))
