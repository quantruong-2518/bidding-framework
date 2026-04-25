"""LLM provider + model selection (Phase 3.7).

Replaces :mod:`config.claude` as the canonical LLM configuration. The
old module stays as a thin re-export shim until commit 3.7c, then is
deleted in commit 3.7c when env names settle.

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
``GOOGLE_API_KEY``). We deliberately don't surface them here so we don't
double-handle secrets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "LLMSettings",
    "LLMProvider",
    "PROVIDER_DEFAULTS",
    "get_llm_settings",
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
