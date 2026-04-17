"""Unit tests for RAG pipeline — chunker, filter builder, rerank fallback."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from rag.indexer import chunk_markdown
from rag.retriever import RetrievalHit, RetrievalQuery, build_qdrant_filter, rerank


def test_chunk_markdown_heading_split() -> None:
    """Chunker respects H2 headings as primary boundaries."""
    doc = (
        "# Title\n\nIntro paragraph.\n\n"
        "## Section A\nContent A paragraph.\n\n"
        "## Section B\nContent B paragraph.\n\n"
        "## Section C\nContent C paragraph.\n"
    )
    chunks = chunk_markdown(doc, max_tokens=512, overlap_tokens=64)
    # Title+intro is before the first ##, so it stays as its own chunk.
    # Each ## section becomes its own chunk (small enough not to window-split).
    assert len(chunks) == 4
    assert chunks[0].startswith("# Title")
    assert chunks[1].startswith("## Section A")
    assert chunks[2].startswith("## Section B")
    assert chunks[3].startswith("## Section C")


def test_chunk_markdown_overlap() -> None:
    """Oversized sections window-split with configured character overlap."""
    body = "## Big\n" + ("abcdefghij " * 500)  # ~5500 chars -> must window
    chunks = chunk_markdown(body, max_tokens=128, overlap_tokens=32)
    assert len(chunks) > 1
    max_chars = 128 * 4
    overlap_chars = 32 * 4
    # Every chunk fits the window.
    assert all(len(c) <= max_chars for c in chunks)
    # Consecutive chunks share an overlap tail equal to overlap_chars.
    tail = chunks[0][-overlap_chars:]
    head = chunks[1][:overlap_chars]
    assert tail == head


def test_chunk_markdown_empty_returns_empty() -> None:
    """Empty input returns an empty list, no false chunks."""
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n  \n") == []


def test_retrieval_query_filter_construction() -> None:
    """build_qdrant_filter maps the filter dict to must/should FieldConditions."""
    q = RetrievalQuery(
        query="core banking migration",
        filters={"domain": "banking", "year": 2023, "client": ["AcmeCorp", "VestaBank"]},
    )
    qfilter = build_qdrant_filter(q.filters)
    assert qfilter is not None
    must_keys = {c.key for c in (qfilter.must or [])}
    should_keys = {c.key for c in (qfilter.should or [])}
    # Scalar values go to must, list values go to should (OR semantics).
    assert "domain" in must_keys
    assert "year" in must_keys
    assert "client" in should_keys
    # Two clients -> two should clauses.
    client_conditions = [c for c in (qfilter.should or []) if c.key == "client"]
    assert len(client_conditions) == 2


def test_retrieval_query_filter_empty_is_none() -> None:
    """No filters -> None (avoids sending empty Filter to Qdrant)."""
    assert build_qdrant_filter({}) is None


@pytest.mark.asyncio
async def test_rerank_fallback_trims_to_final_k() -> None:
    """With no COHERE_API_KEY, rerank returns deterministic top final_k."""
    hits = [
        RetrievalHit(content=f"doc-{i}", score=1.0 - i * 0.1, metadata={"i": i}, chunk_index=0)
        for i in range(8)
    ]
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("COHERE_API_KEY", None)
        out = await rerank(hits, "query", final_k=3)
    assert len(out) == 3
    assert [h.content for h in out] == ["doc-0", "doc-1", "doc-2"]


@pytest.mark.asyncio
async def test_rerank_empty_hits_returns_empty() -> None:
    """Empty hits is a no-op regardless of key presence."""
    out = await rerank([], "query", final_k=5)
    assert out == []


@pytest.mark.asyncio
async def test_hybrid_search_uses_query_points_with_mocked_client() -> None:
    """hybrid_search calls AsyncQdrantClient.query_points with prefetch + fusion."""
    from rag.retriever import hybrid_search

    # Mock embedders so no model load.
    class _Sparse:
        indices = [1, 2, 3]
        values = [0.4, 0.3, 0.3]

    dense_mock = AsyncMock()
    dense_mock.embed_batch = AsyncMock(return_value=[[0.1] * 384])
    sparse_mock = AsyncMock()
    sparse_mock.embed_batch = AsyncMock(return_value=[_Sparse()])

    # Fake Qdrant response points.
    class _P:
        def __init__(self, content: str, score: float, idx: int) -> None:
            self.payload = {"content": content, "chunk_index": idx, "domain": "banking"}
            self.score = score

    class _Result:
        points = [_P("a", 0.9, 0), _P("b", 0.8, 1)]

    client = AsyncMock()
    client.query_points = AsyncMock(return_value=_Result())

    with (
        patch("rag.retriever.get_dense_embedder", return_value=dense_mock),
        patch("rag.retriever.get_sparse_embedder", return_value=sparse_mock),
    ):
        hits = await hybrid_search(
            client,
            RetrievalQuery(query="migration", filters={"domain": "banking"}, top_k=5, final_k=2),
        )

    assert len(hits) == 2
    assert hits[0].content == "a"
    client.query_points.assert_awaited_once()
    kwargs = client.query_points.await_args.kwargs
    assert "prefetch" in kwargs
    assert len(kwargs["prefetch"]) == 2
