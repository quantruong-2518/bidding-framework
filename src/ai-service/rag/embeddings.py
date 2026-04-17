"""Dense + sparse embedding providers (fastembed default, Voyage optional)."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from config.embeddings import get_embedding_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SparseVector:
    """Sparse vector payload used by Qdrant hybrid search."""

    indices: list[int]
    values: list[float]


class EmbeddingProvider(ABC):
    """Abstract dense embedding provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Model name identifier."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dense vector dimensionality."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return dense vectors."""


class SparseProvider(ABC):
    """Abstract sparse embedding provider (BM25-like)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Model name identifier."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[SparseVector]:
        """Embed a batch of texts and return sparse vectors."""


class FastEmbedDenseProvider(EmbeddingProvider):
    """Self-hosted dense provider using fastembed + BAAI/bge-small-en-v1.5."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dim: int = 384) -> None:
        self._model_name = model_name
        self._dim = dim
        self._model = None  # lazy; loading ONNX model at import time is expensive

    def _load(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import anyio

        model = self._load()

        def _run() -> list[list[float]]:
            # fastembed is sync; offload to thread to keep the event loop clean.
            return [vec.tolist() for vec in model.embed(texts)]

        return await anyio.to_thread.run_sync(_run)


class FastEmbedSparseProvider(SparseProvider):
    """Self-hosted sparse provider using fastembed Qdrant/bm25."""

    def __init__(self, model_name: str = "Qdrant/bm25") -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            from fastembed import SparseTextEmbedding

            self._model = SparseTextEmbedding(model_name=self._model_name)
        return self._model

    @property
    def name(self) -> str:
        return self._model_name

    async def embed_batch(self, texts: list[str]) -> list[SparseVector]:
        import anyio

        model = self._load()

        def _run() -> list[SparseVector]:
            out: list[SparseVector] = []
            for vec in model.embed(texts):
                out.append(
                    SparseVector(
                        indices=[int(i) for i in vec.indices.tolist()],
                        values=[float(v) for v in vec.values.tolist()],
                    )
                )
            return out

        return await anyio.to_thread.run_sync(_run)


class VoyageDenseProvider(EmbeddingProvider):
    """Optional Voyage AI provider (used only when VOYAGE_API_KEY is set)."""

    def __init__(self, model_name: str = "voyage-3", dim: int = 1024) -> None:
        self._model_name = model_name
        self._dim = dim
        self._api_key = os.getenv("VOYAGE_API_KEY")
        if not self._api_key:
            raise RuntimeError("VOYAGE_API_KEY not set")

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model_name, "input": texts, "input_type": "document"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]


@lru_cache(maxsize=1)
def get_dense_embedder() -> EmbeddingProvider:
    """Return the configured dense embedder (fastembed by default)."""
    settings = get_embedding_settings()
    provider = settings.provider.lower()
    if provider == "voyage" and os.getenv("VOYAGE_API_KEY"):
        logger.info("embeddings.dense provider=voyage model=%s", settings.voyage_model)
        return VoyageDenseProvider(model_name=settings.voyage_model)
    logger.info("embeddings.dense provider=fastembed model=%s", settings.dense_model)
    return FastEmbedDenseProvider(model_name=settings.dense_model, dim=settings.dense_dim)


@lru_cache(maxsize=1)
def get_sparse_embedder() -> SparseProvider:
    """Return the configured sparse embedder (BM25 via fastembed)."""
    settings = get_embedding_settings()
    logger.info("embeddings.sparse provider=fastembed model=%s", settings.sparse_model)
    return FastEmbedSparseProvider(model_name=settings.sparse_model)
