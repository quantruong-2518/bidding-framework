"""LLM provider + model selection (Phase 3.7).

Canonical LLM configuration. :mod:`config.claude` stays as a compat
shim that re-exports ``HAIKU`` / ``SONNET`` constants and a thin
``ClaudeSettings.api_key`` property which still proxies
``ANTHROPIC_API_KEY``; activity-level "is the LLM available?" checks
should call :func:`is_llm_available` here instead so they're
provider-aware.

Environment::

    LLM_PROVIDER=anthropic           # anthropic | openai | bedrock | gemini
    LLM_MODEL_REASONING=...          # full LiteLLM ID; falls back per provider
    LLM_MODEL_EXTRACTION=...         # ditto
    LLM_TIMEOUT_S=30
    LLM_MAX_RETRIES=3
    LLM_RETRY_INITIAL_WAIT_S=1
    LLM_RETRY_MAX_WAIT_S=16

Per-provider API keys are read by LiteLLM from its own conventional env
vars (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``AWS_ACCESS_KEY_ID``,
``GOOGLE_API_KEY``). :func:`is_llm_available` checks the env var that
matches :attr:`LLMSettings.provider` so a Bid-M run with
``LLM_PROVIDER=openai`` + ``OPENAI_API_KEY=...`` correctly picks the
real path even when ``ANTHROPIC_API_KEY`` is absent.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "LLMSettings",
    "LLMProvider",
    "PROVIDER_DEFAULTS",
    "PROVIDER_KEY_VARS",
    "get_llm_settings",
    "is_llm_available",
]

LLMProvider = Literal["anthropic", "openai", "bedrock", "gemini"]

# Sane defaults per provider. User can override either via
# LLM_MODEL_REASONING / _EXTRACTION env. When unset we route reasoning to
# the provider's flagship and extraction to its small/fast variant.
PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "anthropic": (
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
    ),
    "openai": (
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
    ),
    "bedrock": (
        "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    ),
    "gemini": (
        "gemini/gemini-1.5-pro",
        "gemini/gemini-1.5-flash",
    ),
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


class LLMSettings(BaseSettings):
    """Process-wide LLM config. Read once via :func:`get_llm_settings`."""

    model_config = SettingsConfigDict(env_prefix="LLM_", case_sensitive=False)

    provider: LLMProvider = "anthropic"
    # Both fields stay ``None`` by default; the resolver picks the
    # provider's flagship when not overridden. Setting only the env you
    # care about (e.g. just ``LLM_MODEL_EXTRACTION=openai/gpt-4o-mini``)
    # is supported.
    model_reasoning: str | None = None
    model_extraction: str | None = None

    timeout_s: float = 30.0
    max_retries: int = 3
    retry_initial_wait_s: float = 1.0
    retry_max_wait_s: float = 16.0

    def resolved_model(self, role: Literal["reasoning", "extraction"]) -> str:
        """Pick the LiteLLM model ID for a role.

        Order:
        1. Explicit ``LLM_MODEL_REASONING`` / ``_EXTRACTION``.
        2. Provider default from :data:`PROVIDER_DEFAULTS`.
        """
        if role == "reasoning":
            override = self.model_reasoning
            default = PROVIDER_DEFAULTS[self.provider][0]
        else:
            override = self.model_extraction
            default = PROVIDER_DEFAULTS[self.provider][1]
        return override or default


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
