"""Document indexing: chunk -> embed (dense+sparse) -> upsert to Qdrant."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from config.qdrant import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_qdrant_settings,
)
from rag.embeddings import get_dense_embedder, get_sparse_embedder
from rag.tenant import SHARED_TENANT

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4  # rough heuristic; avoids pulling a tokenizer for chunking
_DEFAULT_MAX_TOKENS = 512
_DEFAULT_OVERLAP_TOKENS = 64
_UPSERT_BATCH = 64


class DocumentMetadata(BaseModel):
    """Structured metadata indexed alongside each chunk."""

    # Phase 3.4-A: payload column kb_search filters on. None falls back to
    # SHARED_TENANT at index time so legacy seed data stays cross-tenant.
    tenant_id: str | None = None
    client: str | None = None
    domain: str | None = None
    project_id: str | None = None
    year: int | None = None
    doc_type: str | None = None
    source_path: str | None = None
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)


class Document(BaseModel):
    """A source document to be chunked and indexed."""

    id: str
    content: str
    metadata: DocumentMetadata


def _split_by_headings(text: str) -> list[str]:
    """Split markdown on H2+ headings, keeping the heading with its section."""
    parts = re.split(r"(?m)^(?=##\s)", text)
    return [p.strip() for p in parts if p.strip()]


def _window(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Sliding-window split on character count with overlap."""
    if len(text) <= max_chars:
        return [text]
    stride = max(1, max_chars - overlap_chars)
    chunks: list[str] = []
    for start in range(0, len(text), stride):
        chunk = text[start : start + max_chars]
        if chunk:
            chunks.append(chunk)
        if start + max_chars >= len(text):
            break
    return chunks


def chunk_markdown(
    text: str,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS,
) -> list[str]:
    """Heading-aware markdown chunker with a character-window fallback."""
    if not text.strip():
        return []
    max_chars = max_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    sections = _split_by_headings(text)
    if not sections:
        sections = [text]

    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            chunks.extend(_window(section, max_chars, overlap_chars))
    return chunks


def _chunk_point_id(parent_id: str, chunk_index: int) -> str:
    """Derive a stable UUID5 so re-indexing is idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{parent_id}::{chunk_index}"))


async def _flush_batch(  # type: ignore[no-untyped-def]
    client,
    collection: str,
    points: list,
) -> None:
    if not points:
        return
    await client.upsert(collection_name=collection, points=points, wait=True)


async def index_documents(  # type: ignore[no-untyped-def]
    client,
    docs: list[Document],
) -> int:
    """Chunk, embed, and upsert a batch of documents. Returns chunks indexed."""
    from qdrant_client.http import models as qm

    settings = get_qdrant_settings()
    dense = get_dense_embedder()
    sparse = get_sparse_embedder()

    all_chunks: list[tuple[Document, int, str]] = []
    for doc in docs:
        for idx, chunk in enumerate(chunk_markdown(doc.content)):
            all_chunks.append((doc, idx, chunk))
    if not all_chunks:
        return 0

    texts = [c for _, _, c in all_chunks]
    dense_vecs = await dense.embed_batch(texts)
    sparse_vecs = await sparse.embed_batch(texts)

    pending: list = []
    total = 0
    for (doc, chunk_idx, chunk_text), dvec, svec in zip(
        all_chunks, dense_vecs, sparse_vecs, strict=True
    ):
        payload = {
            "content": chunk_text,
            "parent_doc_id": doc.id,
            "chunk_index": chunk_idx,
            **doc.metadata.model_dump(exclude_none=True, exclude={"extra"}),
            **doc.metadata.extra,
        }
        # Phase 3.4-A: every chunk MUST carry a tenant_id so cross-tenant
        # leakage is impossible at filter time. Default to SHARED_TENANT
        # for cross-tenant content (lessons/, technologies/, …).
        payload.setdefault("tenant_id", SHARED_TENANT)
        point = qm.PointStruct(
            id=_chunk_point_id(doc.id, chunk_idx),
            vector={
                DENSE_VECTOR_NAME: dvec,
                SPARSE_VECTOR_NAME: qm.SparseVector(indices=svec.indices, values=svec.values),
            },
            payload=payload,
        )
        pending.append(point)
        if len(pending) >= _UPSERT_BATCH:
            await _flush_batch(client, settings.collection_name, pending)
            total += len(pending)
            pending = []
    if pending:
        await _flush_batch(client, settings.collection_name, pending)
        total += len(pending)

    logger.info("rag.index_documents chunks=%d docs=%d", total, len(docs))
    return total


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse a tiny subset of YAML frontmatter (key: value lines) without PyYAML."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm_block, body = match.group(1), match.group(2)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def _coerce_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def index_markdown_file(  # type: ignore[no-untyped-def]
    client,
    path: str,
    metadata_overrides: dict | None = None,
) -> int:
    """Read a single markdown file (with optional frontmatter) and index it."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(raw)
    overrides = metadata_overrides or {}

    metadata = DocumentMetadata(
        tenant_id=overrides.get("tenant_id") or fm.get("tenant_id"),
        client=overrides.get("client") or fm.get("client"),
        domain=overrides.get("domain") or fm.get("domain"),
        project_id=overrides.get("project_id") or fm.get("project_id"),
        year=overrides.get("year") or _coerce_year(fm.get("year")),
        doc_type=overrides.get("doc_type") or fm.get("doc_type"),
        source_path=overrides.get("source_path") or str(p),
    )
    doc_id = overrides.get("id") or fm.get("project_id") or p.stem
    doc = Document(id=doc_id, content=body, metadata=metadata)
    return await index_documents(client, [doc])
