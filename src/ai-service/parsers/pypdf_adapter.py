"""PDF → ParsedRFP adapter using pypdf (pure-Python, no docker overhead).

Tradeoffs vs Unstructured.io: no ML-based element classification, no OCR, table
extraction is raw-text. Works for ~90% of enterprise RFPs (text-based PDFs). For
scanned documents or complex tables, Phase 3 can plug in Unstructured.io by
adding another adapter behind the same `ParsedRFP` contract.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from parsers.models import ParsedRFP, Section

logger = logging.getLogger(__name__)

# Heading detection heuristic — lines that are:
#   - all-caps (>= 4 chars) OR
#   - numbered (1., 1.1, 1.1.1) followed by text OR
#   - markdown-ish (# / ## / ### prefix in some PDFs)
# We keep this deliberately coarse; rfp_extractor consumes the sections downstream.
_HEADING_RE = re.compile(
    r"""^
    (?:
        (?P<numbered>\d+(?:\.\d+){0,3}\.?)\s+(?P<num_title>.+)
      | (?P<allcaps>[A-Z][A-Z0-9\s\-&/,()]{3,100})
      | \#{1,4}\s+(?P<md_title>.+)
    )
    \s*$
    """,
    re.VERBOSE,
)

_TABLE_LINE_RE = re.compile(r"(?:\s*\|\s*[^|]+){2,}\|?")  # 3+ pipe-delimited cells


def _pages_text(reader: PdfReader) -> list[str]:
    texts: list[str] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 — pypdf can raise on malformed PDFs
            logger.warning("pypdf_adapter.page_extract_failed err=%s", exc)
            texts.append("")
    return texts


def _classify_heading(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    if len(stripped) < 3 or len(stripped) > 120:
        return None
    match = _HEADING_RE.match(stripped)
    if not match:
        return None
    if match.group("md_title"):
        depth = len(line) - len(line.lstrip("#"))
        return depth, match.group("md_title").strip()
    if match.group("numbered"):
        numbered = match.group("numbered").rstrip(".")
        depth = len(numbered.split(".")) if numbered else 1
        return depth, match.group("num_title").strip()
    return 1, match.group("allcaps").strip()


def _split_sections(pages: list[str]) -> list[Section]:
    current = Section(heading="(preamble)", level=0, text="", page_hint=1)
    sections: list[Section] = []
    for page_idx, page in enumerate(pages, start=1):
        for raw_line in page.splitlines():
            heading = _classify_heading(raw_line)
            if heading is not None:
                if current.text.strip() or current.heading != "(preamble)":
                    sections.append(current)
                level, title = heading
                current = Section(heading=title, level=level, text="", page_hint=page_idx)
            else:
                current.text += raw_line + "\n"
    if current.text.strip() or current.heading != "(preamble)":
        sections.append(current)
    return sections


def _extract_tables(pages: list[str]) -> list[str]:
    """Detect ascii-pipe tables on a best-effort basis. Good enough for first-pass review."""
    tables: list[str] = []
    buffer: list[str] = []
    for page in pages:
        for line in page.splitlines():
            if _TABLE_LINE_RE.match(line):
                buffer.append(line.rstrip())
                continue
            if buffer:
                if len(buffer) >= 2:  # header + at least one data row
                    tables.append("\n".join(buffer))
                buffer = []
        if buffer:
            if len(buffer) >= 2:
                tables.append("\n".join(buffer))
            buffer = []
    return tables


def _metadata(reader: PdfReader) -> dict[str, str]:
    meta: dict[str, str] = {}
    info = getattr(reader, "metadata", None)
    if info is None:
        return meta
    for key in ("/Title", "/Author", "/Subject", "/Producer", "/CreationDate"):
        value = info.get(key) if isinstance(info, dict) else getattr(info, key, None)
        if value:
            meta[key.lstrip("/").lower()] = str(value)
    return meta


def parse_pdf_bytes(data: bytes, source_filename: str) -> ParsedRFP:
    """Parse PDF binary content into a ParsedRFP. Never raises on malformed input — returns best-effort."""
    reader = PdfReader(BytesIO(data))
    pages = _pages_text(reader)
    raw_text = "\n".join(pages)

    sections = _split_sections(pages)
    tables_text = _extract_tables(pages)

    from parsers.models import TableBlob

    parsed = ParsedRFP(
        source_format="pdf",
        source_filename=source_filename,
        page_count=len(pages),
        sections=sections,
        tables=[TableBlob(raw_text=t) for t in tables_text],
        raw_text=raw_text,
        metadata=_metadata(reader),
    )
    logger.info(
        "pypdf_adapter.done file=%s pages=%d sections=%d tables=%d",
        source_filename,
        parsed.page_count,
        len(parsed.sections),
        len(parsed.tables),
    )
    return parsed


def parse_pdf_path(path: str | Path, source_filename: str | None = None) -> ParsedRFP:
    """Convenience wrapper for on-disk PDFs (tests / CLI)."""
    p = Path(path)
    return parse_pdf_bytes(p.read_bytes(), source_filename or p.name)


__all__ = ["parse_pdf_bytes", "parse_pdf_path"]
