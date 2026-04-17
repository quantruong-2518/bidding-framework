"""Hybrid retrieval: dense + sparse -> RRF fusion -> optional Cohere rerank."""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from config.qdrant import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_qdrant_settings,
)
from rag.embeddings import get_dense_embedder, get_sparse_embedder

logger = logging.getLogger(__name__)

_FILTER_EQ_KEYS = ("client", "domain", "project_id", "year", "doc_type")


class RetrievalQuery(BaseModel):
    """User-facing retrieval request."""

    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = 20
    final_k: int = 5


class RetrievalHit(BaseModel):
    """Single retrieved chunk, after fusion (and optional rerank)."""

    content: str
    score: float
    metadata: dict[str, Any]
    chunk_index: int


def build_qdrant_filter(filters: dict[str, Any]):  # type: ignore[no-untyped-def]
    """Translate a RetrievalQuery.filters dict into a Qdrant Filter object."""
    from qdrant_client.http import models as qm

    must: list = []
    should: list = []
    for key in _FILTER_EQ_KEYS:
        if key not in filters:
            continue
        value = filters[key]
        if isinstance(value, list):
            should.extend(
                qm.FieldCondition(key=key, match=qm.MatchValue(value=v)) for v in value
            )
        else:
            must.append(qm.FieldCondition(key=key, match=qm.MatchValue(value=value)))

    if not must and not should:
        return None
    return qm.Filter(must=must or None, should=should or None)


def _hit_from_scored_point(point) -> RetrievalHit:  # type: ignore[no-untyped-def]
    payload = point.payload or {}
    return RetrievalHit(
        content=payload.get("content", ""),
        score=float(point.score) if point.score is not None else 0.0,
        metadata={k: v for k, v in payload.items() if k != "content"},
        chunk_index=int(payload.get("chunk_index", 0)),
    )


async def hybrid_search(  # type: ignore[no-untyped-def]
    client,
    query: RetrievalQuery,
) -> list[RetrievalHit]:
    """Dense + sparse prefetch fused via RRF server-side (Qdrant query_points)."""
    from qdrant_client.http import models as qm

    settings = get_qdrant_settings()
    dense = get_dense_embedder()
    sparse = get_sparse_embedder()

    dense_vec = (await dense.embed_batch([query.query]))[0]
    sparse_vec = (await sparse.embed_batch([query.query]))[0]
    qfilter = build_qdrant_filter(query.filters)

    result = await client.query_points(
        collection_name=settings.collection_name,
        prefetch=[
            qm.Prefetch(
                query=dense_vec,
                using=DENSE_VECTOR_NAME,
                limit=query.top_k,
                filter=qfilter,
            ),
            qm.Prefetch(
                query=qm.SparseVector(indices=sparse_vec.indices, values=sparse_vec.values),
                using=SPARSE_VECTOR_NAME,
                limit=query.top_k,
                filter=qfilter,
            ),
        ],
        query=qm.FusionQuery(fusion=qm.Fusion.RRF),
        limit=query.top_k,
        with_payload=True,
    )
    points = getattr(result, "points", result)
    hits = [_hit_from_scored_point(p) for p in points]
    logger.info("rag.hybrid_search q_len=%d hits=%d", len(query.query), len(hits))
    return hits


async def rerank(
    hits: list[RetrievalHit],
    query: str,
    final_k: int,
) -> list[RetrievalHit]:
    """Cohere rerank-english-v3.0 when COHERE_API_KEY set, else deterministic trim."""
    if not hits:
        return []
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        return hits[:final_k]

    # Delayed import keeps cohere optional.
    try:
        import cohere  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("rag.rerank cohere_not_installed fallback=trim")
        return hits[:final_k]

    co = cohere.AsyncClient(api_key=api_key)
    try:
        response = await co.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=[h.content for h in hits],
            top_n=min(final_k, len(hits)),
        )
    finally:
        await co.close()

    reranked: list[RetrievalHit] = []
    for result in response.results:
        src = hits[result.index]
        reranked.append(
            RetrievalHit(
                content=src.content,
                score=float(result.relevance_score),
                metadata=src.metadata,
                chunk_index=src.chunk_index,
            )
        )
    return reranked


async def search(  # type: ignore[no-untyped-def]
    client,
    query: RetrievalQuery,
) -> list[RetrievalHit]:
    """Full pipeline: hybrid fetch -> rerank -> final_k."""
    hits = await hybrid_search(client, query)
    return await rerank(hits, query.query, query.final_k)
