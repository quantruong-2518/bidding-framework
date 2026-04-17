"""Embedding provider configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    """Environment-driven embedding provider settings."""

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", case_sensitive=False)

    provider: str = "fastembed"
    dense_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    dense_dim: int = 384
    batch_size: int = 64
    # Optional: VoyageAI + Cohere rerank keys read from dedicated envs
    voyage_model: str = "voyage-3"


@lru_cache(maxsize=1)
def get_embedding_settings() -> EmbeddingSettings:
    """Process-wide embedding settings singleton."""
    return EmbeddingSettings()
