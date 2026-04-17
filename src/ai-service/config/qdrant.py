"""Qdrant client + collection configuration (named vectors, hybrid)."""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from config.embeddings import get_embedding_settings

logger = logging.getLogger(__name__)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

# Payload keys we always filter / facet on — kept as module constants so
# indexer, retriever, and the collection schema stay in sync.
PAYLOAD_KEYS: tuple[str, ...] = (
    "client",
    "domain",
    "project_id",
    "year",
    "doc_type",
    "source_path",
    "parent_doc_id",
    "chunk_index",
)


class QdrantSettings(BaseSettings):
    """Environment-driven Qdrant connection + collection settings."""

    model_config = SettingsConfigDict(env_prefix="QDRANT_", case_sensitive=False)

    url: str = "http://qdrant:6333"
    api_key: str | None = None
    collection_name: str = "bid_knowledge"
    dense_dim: int = 384
    distance: str = "Cosine"
    prefer_grpc: bool = False


@lru_cache(maxsize=1)
def get_qdrant_settings() -> QdrantSettings:
    """Process-wide Qdrant settings singleton."""
    return QdrantSettings()


async def get_qdrant_client():  # type: ignore[no-untyped-def]
    """Return a connected AsyncQdrantClient; imported lazily to stay light."""
    from qdrant_client import AsyncQdrantClient

    settings = get_qdrant_settings()
    logger.info("qdrant.connect url=%s collection=%s", settings.url, settings.collection_name)
    return AsyncQdrantClient(
        url=settings.url,
        api_key=settings.api_key,
        prefer_grpc=settings.prefer_grpc,
    )


async def ensure_collection(client) -> None:  # type: ignore[no-untyped-def]
    """Idempotently create the hybrid collection + payload indexes."""
    from qdrant_client.http import models as qm

    settings = get_qdrant_settings()
    emb = get_embedding_settings()

    exists = await client.collection_exists(settings.collection_name)
    if not exists:
        await client.create_collection(
            collection_name=settings.collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: qm.VectorParams(
                    size=emb.dense_dim,
                    distance=qm.Distance[settings.distance.upper()],
                ),
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: qm.SparseVectorParams(
                    index=qm.SparseIndexParams(on_disk=False),
                ),
            },
        )
        logger.info("qdrant.collection_created name=%s", settings.collection_name)

    # Payload indexes enable fast metadata filtering for BA/SA agents.
    for field in ("client", "domain", "project_id", "year", "doc_type"):
        try:
            await client.create_payload_index(
                collection_name=settings.collection_name,
                field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD
                if field != "year"
                else qm.PayloadSchemaType.INTEGER,
            )
        except Exception as exc:  # noqa: BLE001 — idempotent best-effort
            logger.debug("qdrant.payload_index_skip field=%s err=%s", field, exc)
