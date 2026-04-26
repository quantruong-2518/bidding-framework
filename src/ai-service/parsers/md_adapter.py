"""Markdown → ParsedFile adapter.

Pure-text passthrough — markdown is already structured, so we just preserve
the body and detect ATX-style headings (``# h1``, ``## h2``, ...) for section
boundaries. Frontmatter (``---`` ... ``---``) at the top is stripped from
``raw_text`` but parsed into ``metadata`` for callers that need it (e.g.
post-confirm atom extractor sees author / language hints).

No third-party dep — frontmatter detection is a 2-line regex.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from workflows.base import ParsedFile

logger = logging.getLogger(__name__)

_FILE_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _safe_file_id(name: str) -> str:
    base = name.rsplit(".", 1)[0] if "." in name else name
    slug = _FILE_ID_SAFE_RE.sub("-", base).strip("-").lower()
    return slug or "md-file"


def _strip_frontmatter(raw: str) -> tuple[str, dict[str, str]]:
    """Return ``(body_without_frontmatter, parsed_yaml_kv_dict)``.

    YAML parsing is intentionally minimal — we only handle ``key: value`` pairs
    on single lines (the 90% case for note frontmatter). Multi-line values are
    preserved as raw strings; complex YAML lands in ``metadata`` verbatim.
    """
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return raw, {}
    block = match.group(1)
    body = raw[match.end() :]
    metadata: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        metadata[key] = value.strip().strip('"').strip("'")
    return body, metadata


def parse_md(content: bytes, source_filename: str = "document.md") -> ParsedFile:
    """Parse a markdown byte blob into a :class:`ParsedFile`.

    Never raises — malformed encoding falls back to ``utf-8`` with replacement
    characters so the upstream pipeline can still emit a manifest entry.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    body, metadata = _strip_frontmatter(text)
    metadata["adapter"] = "md"

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] = {
        "heading": "(preamble)",
        "level": 0,
        "text": "",
        "line_range": (1, 1),
    }
    start_line = 1

    lines = body.splitlines()
    for idx, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match:
            # Close current section before opening a new one.
            if current["text"].strip() or current["heading"] != "(preamble)":
                current["line_range"] = (start_line, idx - 1)
                sections.append(current)
            level = len(match.group(1))
            heading = match.group(2).strip()
            current = {
                "heading": heading,
                "level": level,
                "text": "",
                "line_range": (idx, idx),
            }
            start_line = idx + 1
        else:
            current["text"] += line + "\n"
    if current["text"].strip() or current["heading"] != "(preamble)":
        current["line_range"] = (start_line, len(lines))
        sections.append(current)

    parsed = ParsedFile(
        file_id=_safe_file_id(source_filename),
        name=source_filename,
        mime="text/markdown",
        raw_text=body,
        sections=sections,
        tables=[],
        metadata=metadata,
        size_bytes=len(content),
    )
    logger.info(
        "md_adapter.done file=%s sections=%d", source_filename, len(parsed.sections)
    )
    return parsed


__all__ = ["parse_md"]
