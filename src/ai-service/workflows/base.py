"""Shared primitive types used by both workflow state models and agent I/O.

This module intentionally has zero imports from `workflows.models`,
`workflows.artifacts`, or `agents.*`. It sits at the bottom of the dependency
graph so the higher-level modules (which DO depend on each other) can all
import from here without triggering import cycles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

BidProfile = Literal["S", "M", "L", "XL"]
"""Bid sizing used to pick a pipeline variant (see STATE_MACHINE.md)."""

WorkflowState = Literal[
    "S0",
    "S1",
    "S1_NO_BID",
    "S2",
    "S2_DONE",
    "S3",
    "S4",
    "S5",
    "S6",
    "S7",
    "S8",
    "S9",
    "S9_BLOCKED",
    "S10",
    "S11",
    "S11_DONE",
    # S0.5 — Wave 2A — Project Context Synthesis (parse-confirm gate).
    # Appended at the END so existing transitions don't reorder; conditional
    # skip preserves backward compat for inputs without parse_session_id.
    "S0_5",
]

RequirementCategory = Literal[
    "functional",
    "nfr",
    "technical",
    "compliance",
    "timeline",
    "unclear",
]

TriageRecommendation = Literal["BID", "NO_BID"]


def utcnow() -> datetime:
    """Module-local helper so callers don't need to remember the timezone arg."""
    return datetime.now(timezone.utc)


class RequirementAtom(BaseModel):
    """A single decomposed requirement with its category + trace source."""

    id: str
    text: str
    category: RequirementCategory
    source_section: str | None = None


# ---------------------------------------------------------------------------
# S0.5 — multi-file parse contracts (Wave 2A).
#
# These DTOs travel between api-gateway → ai-service → vault writers. They live
# here (NOT in workflows.models) to keep the dependency graph acyclic — kb_writer
# and parsers/* modules already import from `workflows.base` only.
# ---------------------------------------------------------------------------


# File roles per §3.1 design doc; classifier picks one per uploaded file.
FileRole = Literal["rfp", "appendix", "qa", "reference", "previous_engagement"]


# Atom typing per §3.1 — same vocabulary as RequirementCategory above (kept
# separate so the two semantically different concepts can diverge later).
AtomType = Literal["functional", "nfr", "technical", "compliance", "timeline", "unclear"]
AtomPriority = Literal["MUST", "SHOULD", "COULD", "WONT"]


class IntakeFile(BaseModel):
    """One uploaded file en route from api-gateway to ai-service.

    Two wire formats are accepted:

    1. ``content_b64`` (base64) — inline byte payload. Used by unit tests and
       small-file dev paths.
    2. ``object_store_uri`` (``s3://bucket/key``) — MinIO/S3 reference. Used
       by the production api-gateway path (see ``parse.controller.ts``):
       the gateway uploads the multipart blob to MinIO under
       ``parse_sessions/<sid>/<file_id>.<ext>``, then sends only the URI.
       The router pre-fetches bytes via ``tools.object_store`` before
       handing the file to ``_dispatch_adapter``.

    ``mime`` is the content-type hint; the dispatcher falls back to filename
    extension when the hint is missing or generic. ``original_name`` mirrors
    the gateway field of the same name and falls back to ``name`` if absent.
    """

    name: str = ""
    original_name: str | None = None
    file_id: str | None = None
    mime: str = ""
    content_b64: str = ""
    object_store_uri: str | None = None
    size_bytes: int = 0
    sha256: str | None = None

    def display_name(self) -> str:
        """Stable filename for adapter routing + manifest entries."""
        return self.name or self.original_name or self.file_id or "unknown"


class ParsedFile(BaseModel):
    """Common output of every adapter (PDF / DOCX / XLSX / MD / TXT).

    All adapters produce the same shape so downstream LLM-driven extraction
    treats them identically. ``raw_text`` is the concatenated body for chunk
    extractors; ``sections`` carry heading boundaries for atom-source links.
    """

    file_id: str  # caller-assigned (e.g. "01-rfp-main")
    name: str  # original upload name
    mime: str = ""
    role: FileRole | None = None  # populated post-classify
    language: Literal["en", "vi"] = "en"
    page_count: int | None = None
    raw_text: str = ""
    sections: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    sha256: str | None = None
    size_bytes: int = 0


class AtomSource(BaseModel):
    """Where an atom was extracted FROM. Powers click-through audit + diff."""

    file: str  # vault-relative source path (e.g. "sources/01-rfp-main.md")
    section: str | None = None
    page: int | None = None
    line_range: tuple[int, int] | None = None


class AtomExtraction(BaseModel):
    """Provenance: parser version + confidence + when."""

    parser: str  # "rfp_extractor_v2.1" or "heuristic_v1"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    extracted_at: datetime = Field(default_factory=utcnow)


class AtomVerification(BaseModel):
    """Human-in-loop verification trail; both fields None until reviewer signs off."""

    verified_by: str | None = None
    verified_at: datetime | None = None


class AtomLinks(BaseModel):
    """Cross-atom relationships discovered by extractor or reviewer."""

    depends_on: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)
    refines: str | None = None
    cross_ref: list[str] = Field(default_factory=list)


class AtomFrontmatter(BaseModel):
    """Frontmatter of a single atom file under ``bids/<bid_id>/requirements/``.

    Body markdown lives separately (assembled by atom_emitter); this model
    captures only the YAML frontmatter contract per §3.1 design.
    """

    id: str  # REQ-F-001 / REQ-NFR-001 / etc.
    type: AtomType
    priority: AtomPriority
    category: str  # free-form, e.g. "user_management"

    source: AtomSource
    extraction: AtomExtraction
    verification: AtomVerification = Field(default_factory=AtomVerification)
    links: AtomLinks = Field(default_factory=AtomLinks)

    tags: list[str] = Field(default_factory=list)
    tenant_id: str
    bid_id: str  # post-confirm = bid uuid; pre-confirm = parse_session_id
    role: Literal["requirement_atom"] = "requirement_atom"

    split_recommended: bool = False
    version: int = 1
    supersedes: str | None = None
    superseded_by: str | None = None
    active: bool = True
    ai_generated: bool = True
    approved: bool = False  # gate for prod RAG ingestion


class ManifestFile(BaseModel):
    """One entry in the ``_manifest.json::files`` array."""

    file_id: str
    original_name: str
    mime: str = ""
    sha256: str = ""
    size_bytes: int = 0
    page_count: int | None = None
    role: FileRole | None = None
    language: Literal["en", "vi"] = "en"
    parsed_to: str | None = None
    object_store_uri: str | None = None
    atoms_extracted: int = 0
    extraction_confidence_avg: float = 0.0


class Manifest(BaseModel):
    """``_manifest.json`` — an audit summary of one parse session.

    Written to ``bids/<bid_id>/_manifest.json`` post-confirm; same shape lives
    inside ``parse_sessions.manifest`` JSONB pre-confirm.
    """

    version: int = 1
    bid_id: str = ""
    tenant_id: str = ""
    session_id: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    files: list[ManifestFile] = Field(default_factory=list)
    parser_version: str = "rfp_extractor_v2.1"
    synth_version: str = "synth_v1.0"
