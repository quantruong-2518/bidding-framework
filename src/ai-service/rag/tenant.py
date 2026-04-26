"""Multi-tenant helpers for RAG: stable slugs + path-derived tenant_id.

Convention (Phase 3.4-A):
- Notes under ``kb-vault/clients/<tenant>/...`` belong to ``<tenant>``.
- A flat ``kb-vault/clients/<tenant>.md`` also belongs to ``<tenant>`` (legacy layout).
- Every other location (lessons/, technologies/, templates/, projects/, bids/, root)
  is treated as cross-tenant ``shared`` knowledge.
- Frontmatter ``tenant_id: <slug>`` is the explicit override and wins over path.
"""

from __future__ import annotations

import re
from pathlib import Path

SHARED_TENANT = "shared"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


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
