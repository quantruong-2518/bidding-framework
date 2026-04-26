"""TXT → ParsedFile adapter.

Plain text with no structure — we keep the full body in ``raw_text`` and emit
exactly one section spanning the whole document so atom extractors receive a
consistent shape regardless of the source format.

``line_range`` of the single section spans 1..total_lines so atom-source
links can still pin extracted atoms to a line offset.
"""

from __future__ import annotations

import logging
import re

from workflows.base import ParsedFile

logger = logging.getLogger(__name__)

_FILE_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_file_id(name: str) -> str:
    base = name.rsplit(".", 1)[0] if "." in name else name
    slug = _FILE_ID_SAFE_RE.sub("-", base).strip("-").lower()
    return slug or "txt-file"


def parse_txt(content: bytes, source_filename: str = "document.txt") -> ParsedFile:
    """Parse a TXT byte blob into a :class:`ParsedFile`.

    Decoding errors fall back to UTF-8 with replacement characters; never
    raises so the upstream pipeline can still surface a manifest entry.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)

    sections = [
        {
            "heading": source_filename,
            "level": 1,
            "text": text,
            "line_range": (1, max(1, line_count)),
        }
    ]
    parsed = ParsedFile(
        file_id=_safe_file_id(source_filename),
        name=source_filename,
        mime="text/plain",
        raw_text=text,
        sections=sections,
        tables=[],
        metadata={"adapter": "txt"},
        size_bytes=len(content),
    )
    logger.info(
        "txt_adapter.done file=%s lines=%d", source_filename, line_count
    )
    return parsed


__all__ = ["parse_txt"]
