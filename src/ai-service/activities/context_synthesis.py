"""Wave 2A — S0.5 context synthesis activity.

Two modes (mutually exclusive on input):

* ``preview`` — pre-confirm. Decode each ``IntakeFile``, classify role,
  extract atoms, synth anchor + summary + open_questions, detect
  cross-source conflicts. Returns the lot in-memory; the caller
  (api-gateway) persists into the ``parse_sessions`` row.
* ``materialize`` — post-confirm. The api-gateway hands us the
  parse-session payload (atoms / anchor / summary / manifest /
  conflicts) verbatim and we write the bid vault tree at
  ``<vault>/bids/<bid_id>/`` atomically. No re-parse, no re-LLM.

Stub-fallback gate: ``config.llm.is_llm_available()`` decides which
path the parsers/* modules take. Activity itself NEVER raises on
LLM failure — every parser already has its own degrade-to-stub
contract.

DTOs live INSIDE this module because they're activity-scoped — Pydantic
inputs/outputs only the workflow + router import; no need to add them to
the global :mod:`workflows.artifacts` surface.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field
from temporalio import activity

from parsers.conflict_detector import ConflictItem, detect_conflicts
from parsers.synth import SynthOutput, synthesize_context
from workflows.base import (
    AtomFrontmatter,
    IntakeFile,
    Manifest,
    ManifestFile,
    ParsedFile,
    utcnow,
)

logger = logging.getLogger(__name__)


SynthesisMode = Literal["preview", "materialize"]


class ContextSynthesisInput(BaseModel):
    """Activity input — mode discriminates which branch executes."""

    mode: SynthesisMode
    parse_session_id: str
    tenant_id: str
    lang: Literal["en", "vi"] = "en"
    bid_id: str | None = None  # required for materialize
    files: list[IntakeFile] = Field(default_factory=list)
    # Materialize mode only — payload from parse_sessions row.
    payload: dict[str, Any] | None = None
    vault_root: str = ""


class AtomEntry(BaseModel):
    """Wire shape for one atom — frontmatter + body — going back to api-gateway."""

    frontmatter: AtomFrontmatter
    body_markdown: str


class ContextSynthesisOutput(BaseModel):
    """Activity result. Same shape regardless of mode so the router can pin
    the payload to either parse_sessions (preview) or vault (materialize)."""

    parse_session_id: str
    bid_id: str | None = None
    mode: SynthesisMode
    atoms: list[AtomEntry] = Field(default_factory=list)
    anchor_md: str = ""
    summary_md: str = ""
    open_questions: list[str] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    manifest: Manifest | None = None
    files_written: list[str] = Field(default_factory=list)
    # Per §3.6 sources_preview — short per-file metadata for UI rendering.
    sources_preview: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# File adapter dispatch — keep imports lazy so unit tests not exercising the
# parser path don't drag in pypdf / openpyxl.
# ---------------------------------------------------------------------------


def _decode_b64(payload: str) -> bytes:
    if not payload:
        return b""
    try:
        return base64.b64decode(payload, validate=False)
    except Exception:  # noqa: BLE001 — malformed b64 → empty body
        logger.warning("context_synthesis.decode_b64_failed bytes=%d", len(payload))
        return b""


def _dispatch_adapter(file: IntakeFile) -> ParsedFile:
    """Pick the right adapter from filename + mime."""
    name = (file.name or "").lower()
    raw = _decode_b64(file.content_b64)
    mime = (file.mime or "").lower()
    try:
        if name.endswith(".pdf") or "pdf" in mime:
            from parsers.pypdf_adapter import parse_pdf_bytes

            parsed_rfp = parse_pdf_bytes(raw, file.name)
            return _from_parsed_rfp(parsed_rfp, file)
        if name.endswith(".docx") or "wordprocessingml" in mime:
            from parsers.docx_adapter import parse_docx_bytes

            parsed_rfp = parse_docx_bytes(raw, file.name)
            return _from_parsed_rfp(parsed_rfp, file)
        if name.endswith(".xlsx") or "spreadsheetml" in mime:
            from parsers.xlsx_adapter import parse_xlsx

            return parse_xlsx(raw, file.name)
        if name.endswith(".md") or "markdown" in mime:
            from parsers.md_adapter import parse_md

            return parse_md(raw, file.name)
        if name.endswith(".txt") or mime.startswith("text/plain"):
            from parsers.txt_adapter import parse_txt

            return parse_txt(raw, file.name)
    except Exception as exc:  # noqa: BLE001 — never raise mid-batch
        logger.warning("context_synthesis.adapter_failed file=%s err=%s", file.name, exc)
    # Default to TXT decoder so the file at least has a manifest entry.
    from parsers.txt_adapter import parse_txt

    return parse_txt(raw, file.name or "unknown.txt")


def _from_parsed_rfp(parsed_rfp: Any, file: IntakeFile) -> ParsedFile:
    """Wrap a legacy :class:`parsers.models.ParsedRFP` in the new
    :class:`ParsedFile` shape so the rest of the pipeline stays uniform."""
    sections = [
        {
            "heading": s.heading,
            "level": s.level,
            "text": s.text,
            "page_hint": s.page_hint,
        }
        for s in getattr(parsed_rfp, "sections", [])
    ]
    tables = [
        {"caption": t.caption, "raw_text": t.raw_text, "page_hint": t.page_hint}
        for t in getattr(parsed_rfp, "tables", [])
    ]
    return ParsedFile(
        file_id=_safe_file_id(file.name),
        name=file.name,
        mime=file.mime,
        page_count=getattr(parsed_rfp, "page_count", None),
        raw_text=getattr(parsed_rfp, "raw_text", ""),
        sections=sections,
        tables=tables,
        metadata=dict(getattr(parsed_rfp, "metadata", {})),
        sha256=file.sha256,
        size_bytes=len(file.content_b64) if file.content_b64 else file.size_bytes,
    )


def _safe_file_id(name: str) -> str:
    import re as _re

    base = (name or "file").rsplit(".", 1)[0]
    slug = _re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-").lower()
    return slug or "file"


# ---------------------------------------------------------------------------
# Preview mode — full LLM (or stub) parse pipeline.
# ---------------------------------------------------------------------------


async def _process_file_for_preview(
    upload: IntakeFile,
    *,
    parse_session_id: str,
    tenant_id: str,
    lang: Literal["en", "vi"],
) -> tuple[ParsedFile, list[tuple[AtomFrontmatter, str]]]:
    """Single-file slice of the preview pipeline: adapter dispatch +
    role classify + atom extract.

    Pulled out of :func:`_run_preview` so the FastAPI router can drive an
    incremental loop — it processes files one at a time and updates the
    in-memory parse tracker after each, so the frontend's 2 s preview
    poll sees the atom count grow before synth fires.

    Synth + conflict-detect + manifest assembly intentionally stay in
    :func:`_finalize_preview` — they need the full atom set to be useful
    and re-running the flagship synth per-file would inflate cost ~3-5x.
    """
    from parsers.atom_extractor import extract_atoms
    from parsers.file_classifier import classify_file_role

    parsed = _dispatch_adapter(upload)
    parsed.language = lang  # honour caller's language hint
    try:
        parsed.role = await classify_file_role(
            parsed, bid_id_for_trace=parse_session_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "context_synthesis.classify_failed file=%s err=%s", parsed.name, exc
        )
        parsed.role = "reference"

    atoms = await extract_atoms(
        parsed,
        bid_id=parse_session_id,
        tenant_id=tenant_id,
        lang=lang,
        bid_id_for_trace=parse_session_id,
    )
    return parsed, atoms


async def _finalize_preview(
    *,
    parse_session_id: str,
    tenant_id: str,
    bid_id: str | None,
    lang: Literal["en", "vi"],
    parsed_files: list[ParsedFile],
    all_atoms: list[tuple[AtomFrontmatter, str]],
    per_file_atoms: dict[str, int],
    per_file_conf: dict[str, list[float]],
) -> ContextSynthesisOutput:
    """Run synth + conflict-detect + manifest from accumulated state.

    Both :func:`_run_preview` (batch) and the router's incremental loop
    end at this single call so the output shape is identical regardless
    of how the atoms were collected.
    """
    bid_card = _suggested_bid_card(parsed_files)

    synth: SynthOutput = await synthesize_context(
        parsed_files,
        all_atoms,
        bid_card,
        lang=lang,
        bid_id_for_trace=parse_session_id,
    )
    conflicts: list[ConflictItem] = await detect_conflicts(
        [a[0] for a in all_atoms],
        parsed_files,
        bid_id_for_trace=parse_session_id,
    )
    manifest = _build_manifest(
        parsed_files=parsed_files,
        bid_id=bid_id or "",
        tenant_id=tenant_id,
        session_id=parse_session_id,
        per_file_atoms=per_file_atoms,
        per_file_conf=per_file_conf,
    )
    sources_preview = [
        {
            "file_id": pf.file_id,
            "name": pf.name,
            "role": pf.role,
            "language": pf.language,
            "page_count": pf.page_count,
            "atoms_extracted": per_file_atoms.get(pf.file_id, 0),
        }
        for pf in parsed_files
    ]
    return ContextSynthesisOutput(
        parse_session_id=parse_session_id,
        bid_id=bid_id,
        mode="preview",
        atoms=[
            AtomEntry(frontmatter=front, body_markdown=body)
            for front, body in all_atoms
        ],
        anchor_md=synth.anchor_md,
        summary_md=synth.summary_md,
        open_questions=synth.open_questions,
        conflicts=conflicts,
        manifest=manifest,
        sources_preview=sources_preview,
    )


async def _run_preview(input: ContextSynthesisInput) -> ContextSynthesisOutput:
    """End-to-end parse pipeline. Caller persists output to parse_sessions."""
    parsed_files: list[ParsedFile] = []
    all_atoms: list[tuple[AtomFrontmatter, str]] = []
    per_file_atoms: dict[str, int] = {}
    per_file_conf: dict[str, list[float]] = {}
    for upload in input.files:
        parsed, atoms = await _process_file_for_preview(
            upload,
            parse_session_id=input.parse_session_id,
            tenant_id=input.tenant_id,
            lang=input.lang,
        )
        parsed_files.append(parsed)
        all_atoms.extend(atoms)
        per_file_atoms[parsed.file_id] = len(atoms)
        per_file_conf[parsed.file_id] = [
            front.extraction.confidence for front, _ in atoms
        ]

    return await _finalize_preview(
        parse_session_id=input.parse_session_id,
        tenant_id=input.tenant_id,
        bid_id=input.bid_id,
        lang=input.lang,
        parsed_files=parsed_files,
        all_atoms=all_atoms,
        per_file_atoms=per_file_atoms,
        per_file_conf=per_file_conf,
    )


def _suggested_bid_card(files: list[ParsedFile]) -> Any:
    """Return the BidCardSuggestion built from the primary RFP-role file
    (or first file if none classified yet)."""
    from parsers.models import BidCardSuggestion, ParsedRFP, Section, TableBlob
    from parsers.rfp_extractor import extract_bid_card

    rfp_file = next((f for f in files if f.role == "rfp"), None) or (
        files[0] if files else None
    )
    if rfp_file is None:
        return BidCardSuggestion()

    sections = [
        Section(
            heading=s.get("heading", ""),
            level=s.get("level", 0),
            text=s.get("text", ""),
            page_hint=s.get("page_hint"),
        )
        for s in (rfp_file.sections or [])
    ]
    tables = [
        TableBlob(
            caption=t.get("caption"),
            raw_text=t.get("raw_text", ""),
            page_hint=t.get("page_hint"),
        )
        for t in (rfp_file.tables or [])
    ]
    parsed_rfp = ParsedRFP(
        source_format="txt",  # safe default — extractor doesn't dispatch on format
        source_filename=rfp_file.name,
        page_count=rfp_file.page_count,
        sections=sections,
        tables=tables,
        raw_text=rfp_file.raw_text,
        metadata=rfp_file.metadata,
    )
    return extract_bid_card(parsed_rfp)


def _build_manifest(
    *,
    parsed_files: list[ParsedFile],
    bid_id: str,
    tenant_id: str,
    session_id: str,
    per_file_atoms: dict[str, int],
    per_file_conf: dict[str, list[float]],
) -> Manifest:
    files_meta: list[ManifestFile] = []
    for pf in parsed_files:
        confs = per_file_conf.get(pf.file_id, [])
        avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0
        files_meta.append(
            ManifestFile(
                file_id=pf.file_id,
                original_name=pf.name,
                mime=pf.mime,
                sha256=pf.sha256 or "",
                size_bytes=pf.size_bytes,
                page_count=pf.page_count,
                role=pf.role,
                language=pf.language,
                parsed_to=f"sources/{pf.file_id}.md",
                object_store_uri=None,
                atoms_extracted=per_file_atoms.get(pf.file_id, 0),
                extraction_confidence_avg=avg_conf,
            )
        )
    return Manifest(
        version=1,
        bid_id=bid_id,
        tenant_id=tenant_id,
        session_id=session_id,
        created_at=utcnow(),
        files=files_meta,
    )


# ---------------------------------------------------------------------------
# Materialize mode — vault writes from a confirmed parse_session payload.
# ---------------------------------------------------------------------------


async def _run_materialize(
    input: ContextSynthesisInput,
) -> ContextSynthesisOutput:
    """Write atoms/anchor/summary/manifest/conflicts to the vault. No LLM."""
    if not input.bid_id:
        raise ValueError("materialize mode requires bid_id")
    payload = input.payload or {}
    vault_root = input.vault_root or _default_vault_root()

    written: list[str] = []
    bid_id = input.bid_id

    # 1. Manifest first so any subsequent failure leaves a discoverable record.
    manifest_payload = payload.get("manifest")
    manifest_obj: Manifest | None = None
    if manifest_payload:
        try:
            manifest_obj = Manifest.model_validate(manifest_payload)
            from kb_writer.manifest_writer import write_manifest

            target = write_manifest(vault_root, bid_id, manifest_obj)
            written.append(str(target))
        except Exception as exc:  # noqa: BLE001
            logger.warning("materialize.manifest_failed err=%s", exc)

    # 2. Atoms.
    raw_atoms = payload.get("atoms") or []
    atoms_pairs: list[tuple[AtomFrontmatter, str]] = []
    for entry in raw_atoms:
        try:
            entry_model = AtomEntry.model_validate(entry)
        except Exception as exc:  # noqa: BLE001
            logger.warning("materialize.atom_invalid err=%s", exc)
            continue
        atoms_pairs.append((entry_model.frontmatter, entry_model.body_markdown))

    if atoms_pairs:
        from kb_writer.atom_emitter import write_atoms

        receipt = write_atoms(vault_root, bid_id, atoms_pairs)
        written.extend(receipt.files_written)

    # 3. Anchor + summary.
    anchor_md = str(payload.get("anchor_md") or "")
    summary_md = str(payload.get("summary_md") or "")
    if anchor_md or summary_md:
        from kb_writer.templates import render_anchor, render_summary

        from pathlib import Path

        bid_root = Path(vault_root) / "bids" / str(bid_id)
        bid_root.mkdir(parents=True, exist_ok=True)
        if anchor_md:
            anchor_path = bid_root / "anchor.md"
            anchor_path.write_text(
                render_anchor(
                    anchor_md, bid_id=bid_id, tenant_id=input.tenant_id
                ),
                encoding="utf-8",
            )
            written.append(str(anchor_path))
        if summary_md:
            summary_path = bid_root / "summary.md"
            summary_path.write_text(
                render_summary(
                    summary_md, bid_id=bid_id, tenant_id=input.tenant_id
                ),
                encoding="utf-8",
            )
            written.append(str(summary_path))

    # 4. Conflicts (best-effort, never fatal).
    raw_conflicts = payload.get("conflicts") or []
    conflicts: list[ConflictItem] = []
    for entry in raw_conflicts:
        try:
            conflicts.append(ConflictItem.model_validate(entry))
        except Exception:  # noqa: BLE001
            continue
    if conflicts:
        from pathlib import Path

        bid_root = Path(vault_root) / "bids" / str(bid_id)
        bid_root.mkdir(parents=True, exist_ok=True)
        conflicts_path = bid_root / "conflicts.md"
        body_lines = [
            "# Conflicts detected",
            "",
            f"_{len(conflicts)} cross-source conflict(s)._",
            "",
        ]
        for c in conflicts:
            body_lines.append(
                f"## {c.topic} ({c.severity})\n\n{c.description}\n\n"
                f"- Atoms: {', '.join(c.atoms)}\n- Files: {', '.join(c.files)}\n"
                f"- Proposed: {c.proposed_resolution}\n"
            )
        conflicts_path.write_text("\n".join(body_lines), encoding="utf-8")
        written.append(str(conflicts_path))

    # 5. Pack rebuild — best effort. Atoms feed BA/SA/Domain/Pricing/Review packs.
    if atoms_pairs:
        try:
            from kb_writer.pack_builder import rebuild_packs

            rebuild_packs(vault_root, bid_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("materialize.packs_failed err=%s", exc)

    return ContextSynthesisOutput(
        parse_session_id=input.parse_session_id,
        bid_id=bid_id,
        mode="materialize",
        atoms=[
            AtomEntry(frontmatter=front, body_markdown=body)
            for front, body in atoms_pairs
        ],
        anchor_md=anchor_md,
        summary_md=summary_md,
        open_questions=list(payload.get("open_questions") or []),
        conflicts=conflicts,
        manifest=manifest_obj,
        files_written=written,
    )


def _default_vault_root() -> str:
    """Resolve the active vault root, mirroring the workspace activity."""
    import os

    return os.environ.get("KB_VAULT_PATH", "../kb-vault")


@activity.defn(name="context_synthesis_activity")
async def context_synthesis_activity(
    payload: ContextSynthesisInput,
) -> ContextSynthesisOutput:
    """Temporal activity surface — dispatches by mode."""
    activity.logger.info(
        "context_synthesis.start mode=%s session=%s files=%d",
        payload.mode,
        payload.parse_session_id,
        len(payload.files),
    )
    if payload.mode == "preview":
        return await _run_preview(payload)
    if payload.mode == "materialize":
        return await _run_materialize(payload)
    raise ValueError(f"unknown mode: {payload.mode}")


__all__ = [
    "AtomEntry",
    "ContextSynthesisInput",
    "ContextSynthesisOutput",
    "context_synthesis_activity",
]
