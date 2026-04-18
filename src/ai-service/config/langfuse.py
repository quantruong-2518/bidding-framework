"""Langfuse observability settings — gated by ``LANGFUSE_SECRET_KEY``.

When ``secret_key`` is unset, :class:`tools.langfuse_client.LangfuseTracer`
resolves to a no-op wrapper — Phase 3.5 mirrors the ``ANTHROPIC_API_KEY``
fallback gate so tests + stub-path runs emit zero Langfuse traffic.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class LangfuseSettings(BaseSettings):
    """Environment-driven Langfuse connection settings.

    All fields optional so default dev (no observability profile) leaves the
    tracer in no-op mode. Activating Langfuse = set ``LANGFUSE_SECRET_KEY``.
    """

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_", case_sensitive=False)

    public_key: str | None = None
    secret_key: str | None = None
    host: str = "http://langfuse-server:3000"
    release: str = "phase-3.5"


@lru_cache(maxsize=1)
def get_langfuse_settings() -> LangfuseSettings:
    """Process-wide Langfuse settings singleton."""
    return LangfuseSettings()
