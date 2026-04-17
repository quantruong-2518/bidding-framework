"""Claude API connection + model routing settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Model IDs pinned per Task 1.3 spec — Haiku for extraction, Sonnet for reasoning.
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


class ClaudeSettings(BaseSettings):
    """Environment-driven Anthropic API settings."""

    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_", case_sensitive=False)

    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 2


@lru_cache(maxsize=1)
def get_claude_settings() -> ClaudeSettings:
    """Process-wide Claude settings singleton."""
    return ClaudeSettings()
