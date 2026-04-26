"""Qdrant client + collection configuration (named vectors, hybrid).

S0.5 Wave 2C additions:
* :data:`STAGING_COLLECTION` and :data:`PROD_COLLECTION` constants for the
  two-collection split. The legacy ``collection_name`` (default
  ``bid_knowledge``) stays untouched for pre-S0.5 callers (e.g. seed data,
  ``kb_search`` for non-atom retrieval).
* :func:`ensure_both_collections` bootstraps the two atom collections by
  invoking :func:`ensure_collection` against each — idempotent and safe to
  call from FastAPI startup.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from config.embeddings import get_embedding_settings

logger = logging.getLogger(__name__)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

# S0.5 Wave 2C: two-collection split for the bid-atoms surface.
# - STAGING — every freshly-indexed atom + sources + derived + lessons. Bid-scoped.
# - PROD    — only atoms with ``approved=True AND active=True``. Cross-bid recall surface.
STAGING_COLLECTION = "bid-atoms-staging"
PROD_COLLECTION = "bid-atoms-prod"

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

# Phase 3.4-A multi-tenant + S0.5 per-role payload keys we want indexed for
# fast filter performance. Additive to PAYLOAD_KEYS — every caller that uses
# the legacy keys keeps working.
ROLE_PAYLOAD_KEYS: tuple[str, ...] = (
    "tenant_id",
    "bid_id",
    "role",
    "atom_id",
    "atom_type",
    "priority",
    "approved",
    "active",
    "kind",
    "outcome",
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


async def ensure_collection(client, collection_name: str | None = None) -> None:  # type: ignore[no-untyped-def]
    """Idempotently create the hybrid collection + payload indexes.

    Optional ``collection_name`` arg lets callers (e.g. :func:`ensure_both_collections`)
    target a specific collection without mutating ``QdrantSettings``. When omitted,
    falls back to the legacy ``settings.collection_name`` so pre-S0.5 callers
    are unchanged.
    """
    from qdrant_client.http import models as qm

    settings = get_qdrant_settings()
    emb = get_embedding_settings()
    name = collection_name or settings.collection_name

    exists = await client.collection_exists(name)
    if not exists:
        await client.create_collection(
            collection_name=name,
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
        logger.info("qdrant.collection_created name=%s", name)

    # Payload indexes enable fast metadata filtering for BA/SA agents.
    legacy_fields = ("client", "domain", "project_id", "year", "doc_type")
    role_fields_keyword = (
        "tenant_id",
        "bid_id",
        "role",
        "atom_id",
        "atom_type",
        "priority",
        "kind",
        "outcome",
    )
    role_fields_bool = ("approved", "active")
    for field in legacy_fields:
        try:
            await client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD
                if field != "year"
                else qm.PayloadSchemaType.INTEGER,
            )
        except Exception as exc:  # noqa: BLE001 — idempotent best-effort
            logger.debug("qdrant.payload_index_skip field=%s err=%s", field, exc)
    # S0.5 Wave 2C role-aware payload indexes. Best-effort + idempotent so a
    # pre-existing collection without these fields gracefully gains them on
    # next bootstrap.
    for field in role_fields_keyword:
        try:
            await client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("qdrant.payload_index_skip field=%s err=%s", field, exc)
    for field in role_fields_bool:
        try:
            await client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qm.PayloadSchemaType.BOOL,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("qdrant.payload_index_skip field=%s err=%s", field, exc)


async def ensure_both_collections(client) -> None:  # type: ignore[no-untyped-def]
    """Bootstrap both ``bid-atoms-staging`` and ``bid-atoms-prod`` collections.

    Calls :func:`ensure_collection` for each name. Idempotent — safe to invoke
    multiple times (e.g. once at FastAPI startup and once at first ingestion).
    The legacy single-collection bootstrap (without arg) remains untouched.
    """
    for name in (STAGING_COLLECTION, PROD_COLLECTION):
        await ensure_collection(client, name)


__all__ = [
    "DENSE_VECTOR_NAME",
    "PAYLOAD_KEYS",
    "PROD_COLLECTION",
    "QdrantSettings",
    "ROLE_PAYLOAD_KEYS",
    "SPARSE_VECTOR_NAME",
    "STAGING_COLLECTION",
    "ensure_both_collections",
    "ensure_collection",
    "get_qdrant_client",
    "get_qdrant_settings",
]
