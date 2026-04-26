"""Multi-tenant + per-role helpers for RAG: stable slugs + path-derived tenant_id.

Convention (Phase 3.4-A):
- Notes under ``kb-vault/clients/<tenant>/...`` belong to ``<tenant>``.
- A flat ``kb-vault/clients/<tenant>.md`` also belongs to ``<tenant>`` (legacy layout).
- Every other location (lessons/, technologies/, templates/, projects/, bids/, root)
  is treated as cross-tenant ``shared`` knowledge.
- Frontmatter ``tenant_id: <slug>`` is the explicit override and wins over path.

S0.5 Wave 2C extension:
- :func:`build_role_filter` composes a Qdrant ``Filter`` from the new RAG
  payload schema (``role``, ``atom_type``, ``priority``, ``approved``,
  ``active``, ``kind``, ``outcome``) on top of the mandatory ``tenant_id``
  must-clause. Existing :func:`rag.retriever.build_qdrant_filter` is
  backward-compatible (Conv-13 contract); this helper is additive and only
  used by callers that need the post-S0.5 metadata gates.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHARED_TENANT = "shared"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


# Field names that build_role_filter knows how to translate. Kept in sync with
# rag.payload_schema.RAGPayload field names so a typo on the caller side gets
# silently dropped instead of generating a confusing Qdrant error.
_ROLE_FILTER_KEYS: tuple[str, ...] = (
    "tenant_id",
    "bid_id",
    "role",
    "atom_type",
    "priority",
    "approved",
    "active",
    "kind",
    "outcome",
)


def slugify(name: str) -> str:
    """Lowercase, ascii-fold, collapse non-alphanumerics to single hyphens."""
    if not name:
        return ""
    lowered = name.strip().lower()
    slug = _SLUG_STRIP.sub("-", lowered).strip("-")
    return slug or ""


def derive_tenant_id_from_path(path: Path | str, vault_root: Path | str) -> str:
    """Map a vault-absolute path to a tenant slug; ``shared`` outside ``clients/``."""
    p = Path(path).resolve()
    root = Path(vault_root).resolve()
    try:
        relative = p.relative_to(root)
    except ValueError:
        return SHARED_TENANT
    return derive_tenant_id_from_relative_path(relative)


def derive_tenant_id_from_relative_path(relative_path: Path | str) -> str:
    """Vault-relative variant; useful when only the relative path is at hand."""
    parts = Path(relative_path).parts
    if not parts or parts[0] != "clients":
        return SHARED_TENANT
    if len(parts) >= 3:
        # clients/<tenant>/<...>.md
        return slugify(parts[1]) or SHARED_TENANT
    if len(parts) == 2:
        # clients/<tenant>.md (legacy flat layout)
        return slugify(Path(parts[1]).stem) or SHARED_TENANT
    return SHARED_TENANT


def build_role_filter(filters: dict[str, Any]):  # type: ignore[no-untyped-def]
    """Compose a Qdrant ``Filter`` over the post-S0.5 RAG payload schema.

    Behaviour:
    - ``tenant_id`` MUST be present and non-empty (Conv-13 contract). Pass
      ``[tenant, SHARED_TENANT]`` to widen to shared content.
    - Any additional key from :data:`_ROLE_FILTER_KEYS` is added as a Qdrant
      ``MatchValue`` condition. List values map to OR'd ``should`` clauses;
      scalar values map to ``must`` clauses.
    - Unknown keys are silently dropped — composition stays additive so future
      extensions can call this without breaking older callers.

    Returns a Qdrant ``Filter`` instance, or raises :class:`ValueError` if
    ``tenant_id`` is missing/empty (rather than silently leaking across
    tenants).
    """
    from qdrant_client.http import models as qm

    tenant = filters.get("tenant_id")
    if tenant is None or (isinstance(tenant, str) and not tenant.strip()):
        raise ValueError("build_role_filter requires a non-empty tenant_id")

    must: list = []
    should: list = []
    for key in _ROLE_FILTER_KEYS:
        if key not in filters:
            continue
        value = filters[key]
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            should.extend(
                qm.FieldCondition(key=key, match=qm.MatchValue(value=v)) for v in value
            )
        else:
            must.append(qm.FieldCondition(key=key, match=qm.MatchValue(value=value)))

    return qm.Filter(must=must or None, should=should or None)


__all__ = [
    "SHARED_TENANT",
    "build_role_filter",
    "derive_tenant_id_from_path",
    "derive_tenant_id_from_relative_path",
    "slugify",
]
