"""S0.5 Wave 2C — per-role Qdrant payload schema.

Each chunk indexed into Qdrant carries a structured payload whose shape depends
on the *role* of the source content. The four roles are aligned with the 5-level
vault layout introduced by the S0.5 design doc §3.5:

* ``source``            — raw extracted markdown from uploaded RFP files
                          (``bids/<bid_id>/sources/*.md``).
* ``requirement_atom``  — atomized requirements (``bids/<bid_id>/requirements/*.md``).
                          The only role gated for the ``bid-atoms-prod`` collection
                          (``approved=True`` + ``active=True``).
* ``derived``           — derived artefacts (compliance matrix, win themes, risk
                          register, open questions, conflicts).
* ``lesson``            — retrospective KB deltas from Conv-15
                          (``clients/<tenant>/lessons/*.md``).

Each role has a dedicated Pydantic model with required + optional fields. The
helper :func:`validate_payload` is used by the indexer to coerce a free-form
payload dict into a typed model and route it correctly.

Backward-compatibility notes (Rule B):
* All models accept ``extra="allow"`` so legacy payload keys (``content``,
  ``parent_doc_id``, ``chunk_index``, ``client``, ``domain``, ``project_id``,
  ``year``, ``doc_type``, ``source_path``) continue to flow through Qdrant
  unchanged. Existing retrievers do not need to be updated.
* :func:`validate_payload` returns ``None`` when validation fails so the caller
  can fall back to the legacy ``staging``-only routing.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# Role literal — the dispatch key for the per-role models below.
PayloadRole = Literal["source", "requirement_atom", "derived", "lesson"]

# Atom type / priority literals mirror ai-service/workflows/base.py::AtomFrontmatter
# so the indexer rejects bad values eagerly. New literals append to the end so
# existing payloads stay valid (Rule B).
AtomType = Literal[
    "functional",
    "nfr",
    "technical",
    "compliance",
    "timeline",
    "unclear",
]
AtomPriority = Literal["MUST", "SHOULD", "COULD", "WONT"]

# Kind literal for the `derived` role; matches the file stems under
# ``bids/<bid_id>/`` listed in §3.5.
DerivedKind = Literal[
    "compliance_matrix",
    "win_themes",
    "risk_register",
    "open_questions",
    "conflicts",
]

# Outcome literal for retrospective lessons (Conv-15 contract).
LessonOutcome = Literal["WON", "LOST", "WITHDRAWN", "BLOCKED"]


class _BasePayload(BaseModel):
    """Common payload fields every role carries."""

    model_config = ConfigDict(extra="allow")

    tenant_id: str = Field(..., min_length=1, description="Multi-tenant filter key (Conv-13).")
    bid_id: str = Field(..., min_length=1)
    role: PayloadRole


class SourcePayload(_BasePayload):
    """Raw RFP source markdown chunk.

    Always routes to the ``staging`` collection — sources are bid-scoped and
    never promoted to the cross-bid prod recall surface.
    """

    role: Literal["source"] = "source"
    file_id: str = Field(..., min_length=1)
    section: str | None = None
    chunk_idx: int = Field(..., ge=0)
    page: int | None = None
    language: Literal["en", "vi"] | None = None


class AtomPayload(_BasePayload):
    """Requirement atom chunk — the only role eligible for the prod collection.

    The indexer routes atoms with ``approved=True AND active=True`` to
    ``bid-atoms-prod``; everything else stays in ``bid-atoms-staging``.
    """

    role: Literal["requirement_atom"] = "requirement_atom"
    atom_id: str = Field(..., min_length=1)
    atom_type: AtomType
    priority: AtomPriority
    approved: bool
    active: bool
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    source_file: str | None = None


class DerivedPayload(_BasePayload):
    """Derived artefact (compliance matrix / risks / win-themes / etc.)."""

    role: Literal["derived"] = "derived"
    kind: DerivedKind


class LessonPayload(_BasePayload):
    """Retrospective KB delta (Conv-15 lesson layout)."""

    role: Literal["lesson"] = "lesson"
    outcome: LessonOutcome
    kb_delta_id: str | None = None


# Discriminated union for downstream callers that want to type-narrow on role.
RAGPayload = Annotated[
    Union[SourcePayload, AtomPayload, DerivedPayload, LessonPayload],
    Field(discriminator="role"),
]


# Mapping from role → payload model class. Used by validate_payload() and
# exposed for reuse by the ingestion service when it needs to know which role
# a frontmatter dict resolves to without instantiating the model first.
_ROLE_TO_MODEL: dict[str, type[_BasePayload]] = {
    "source": SourcePayload,
    "requirement_atom": AtomPayload,
    "derived": DerivedPayload,
    "lesson": LessonPayload,
}


def validate_payload(payload: dict[str, Any], role: str) -> _BasePayload | None:
    """Coerce a payload dict into the role-specific model.

    Returns the validated model on success, ``None`` on validation failure so
    the caller can decide whether to drop the chunk or fall back to legacy
    untyped indexing. The indexer logs the validation error at WARNING level
    so misconfigured frontmatter is surfaced without aborting ingestion.
    """
    model_cls = _ROLE_TO_MODEL.get(role)
    if model_cls is None:
        logger.warning("payload_schema.unknown_role role=%s", role)
        return None
    try:
        return model_cls.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — caller falls back, never aborts
        logger.warning(
            "payload_schema.validation_failed role=%s err=%s",
            role,
            exc,
        )
        return None


def routes_to_prod(payload: _BasePayload) -> bool:
    """Decide whether a validated payload should land in ``bid-atoms-prod``.

    Only ``requirement_atom`` payloads with both ``approved=True`` and
    ``active=True`` qualify. Every other payload routes to ``bid-atoms-staging``.
    """
    if not isinstance(payload, AtomPayload):
        return False
    return bool(payload.approved) and bool(payload.active)


__all__ = [
    "AtomPayload",
    "AtomPriority",
    "AtomType",
    "DerivedKind",
    "DerivedPayload",
    "LessonOutcome",
    "LessonPayload",
    "PayloadRole",
    "RAGPayload",
    "SourcePayload",
    "routes_to_prod",
    "validate_payload",
]
