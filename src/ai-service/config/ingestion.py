"""Settings for the Obsidian vault ingestion service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_vault_path() -> Path:
    """Resolve src/kb-vault relative to this file as a sensible dev default."""
    return Path(__file__).resolve().parents[2] / "kb-vault"


class IngestionSettings(BaseSettings):
    """Environment-driven settings for the ingestion service."""

    model_config = SettingsConfigDict(env_prefix="KB_", case_sensitive=False)

    vault_path: Path = _default_vault_path()
    poll_interval_seconds: float = 5.0
    debounce_ms: int = 500
    hash_cache_path: Path = Path("/tmp/bid-framework/ingestion-hashes.json")
    graph_snapshot_path: Path = Path("/tmp/bid-framework/vault-graph.json")


@lru_cache(maxsize=1)
def get_ingestion_settings() -> IngestionSettings:
    """Process-wide ingestion settings singleton."""
    return IngestionSettings()
