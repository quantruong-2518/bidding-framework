"""Agent-facing KB retrieval: wraps rag.retriever.search with safe degradation."""

from __future__ import annotations

import logging
from typing import Any

from config.qdrant import ensure_collection, get_qdrant_client
from rag.retriever import RetrievalQuery, search
from rag.tenant import SHARED_TENANT

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


def _build_filters(
    *,
    tenant_id: str,
    include_shared: bool,
    domain: str | None,
    client_name: str | None,
) -> dict[str, Any]:
    """Phase 3.4-A: tenant_id filter is mandatory; optionally widen to shared KB."""
    if include_shared and tenant_id != SHARED_TENANT:
        # OR semantics — retriever maps list values onto Qdrant `should` clauses.
        filters: dict[str, Any] = {"tenant_id": [tenant_id, SHARED_TENANT]}
    else:
        filters = {"tenant_id": tenant_id}
    if domain:
        filters["domain"] = domain.lower()
    if client_name:
        filters["client"] = client_name
    return filters


async def kb_search(
    query: str,
    *,
    tenant_id: str,
    include_shared: bool = True,
    domain: str | None = None,
    client: str | None = None,
    final_k: int = 5,
) -> list[dict[str, Any]]:
    """Return JSON-serializable RAG hits; empty list on any retrieval failure.

    Phase 3.4-A: ``tenant_id`` is required to prevent cross-tenant KB leaks.
    Pass ``SHARED_TENANT`` (``"shared"``) explicitly when an admin-scope sweep
    is intended; the call is logged so audits can spot wide searches.
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("kb_search requires a non-empty tenant_id")
    if not query.strip():
        return []

    if tenant_id == SHARED_TENANT and include_shared:
        logger.info("kb_search.cross_tenant_search query_len=%d", len(query))

    qdrant_client = await _lazy_client()
    if qdrant_client is None:
        return []

    request = RetrievalQuery(
        query=query,
        filters=_build_filters(
            tenant_id=tenant_id,
            include_shared=include_shared,
            domain=domain,
            client_name=client,
        ),
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
    logger.info(
        "kb_search.done tenant=%s q_len=%d hits=%d",
        tenant_id,
        len(query),
        len(results),
    )
    return results
