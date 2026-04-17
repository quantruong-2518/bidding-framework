"""Agent-facing KB retrieval: wraps rag.retriever.search with safe degradation."""

from __future__ import annotations

import logging
from typing import Any

from config.qdrant import ensure_collection, get_qdrant_client
from rag.retriever import RetrievalQuery, search

logger = logging.getLogger(__name__)

_collection_ready: bool = False


async def _lazy_client() -> Any | None:
    """Connect + idempotently create collection on first use; cache the readiness flag."""
    global _collection_ready
    try:
        client = await get_qdrant_client()
    except Exception as exc:  # noqa: BLE001 — degrade gracefully if Qdrant is down
        logger.warning("kb_search.qdrant_unavailable err=%s", exc)
        return None

    if not _collection_ready:
        try:
            await ensure_collection(client)
            _collection_ready = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("kb_search.ensure_collection_failed err=%s", exc)
            return None
    return client


def _build_filters(domain: str | None, client_name: str | None) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if domain:
        filters["domain"] = domain.lower()
    if client_name:
        filters["client"] = client_name
    return filters


async def kb_search(
    query: str,
    *,
    domain: str | None = None,
    client: str | None = None,
    final_k: int = 5,
) -> list[dict[str, Any]]:
    """Return JSON-serializable RAG hits; empty list on any retrieval failure."""
    if not query.strip():
        return []

    qdrant_client = await _lazy_client()
    if qdrant_client is None:
        return []

    request = RetrievalQuery(
        query=query,
        filters=_build_filters(domain, client),
        top_k=max(final_k * 4, 10),
        final_k=final_k,
    )
    try:
        hits = await search(qdrant_client, request)
    except Exception as exc:  # noqa: BLE001 — never break the agent for KB glitches
        logger.warning("kb_search.search_failed err=%s", exc)
        return []

    results: list[dict[str, Any]] = []
    for hit in hits:
        meta = dict(hit.metadata)
        source_path = meta.pop("source_path", None)
        results.append(
            {
                "content": hit.content,
                "score": float(hit.score),
                "source_path": source_path,
                "metadata": meta,
            }
        )
    logger.info("kb_search.done q_len=%d hits=%d", len(query), len(results))
    return results
