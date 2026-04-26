"""S0.5 atom extractor — extract requirement atoms from ParsedFile.

Two paths gated by :func:`config.llm.is_llm_available`:

* **LLM path** — small-tier :class:`LLMConversation` chunked at ~8K tokens
  per call, expects a JSON array per chunk. Each atom validated into
  :class:`AtomFrontmatter` + body markdown string.
* **Heuristic stub path** — port of the regex bullet logic from
  ``activities.intake._extract_requirements`` so tests never need a key.
  Each stub atom carries ``ai_generated=False`` + ``confidence=0.5`` per
  §8 of the design doc.

Contract: returns a flat list of ``(AtomFrontmatter, body_markdown)`` tuples.
The wrapper renumbers atoms per-bid using :func:`_assign_atom_ids` so type
prefixes (``REQ-F-001``, ``REQ-NFR-001``, etc.) stay stable across one bid.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.atom_extractor import (
    SYSTEM_PROMPT_ATOM_EXTRACTOR_EN,
    SYSTEM_PROMPT_ATOM_EXTRACTOR_VI,
)
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.base import (
    AtomExtraction,
    AtomFrontmatter,
    AtomLinks,
    AtomPriority,
    AtomSource,
    AtomType,
    AtomVerification,
    ParsedFile,
    utcnow,
)

logger = logging.getLogger(__name__)

_TIER = "small"

# §3.1 — atom id type prefix. Drives both the filename + the AtomFrontmatter.id.
_TYPE_PREFIX: dict[str, str] = {
    "functional": "F",
    "nfr": "NFR",
    "technical": "T",
    "compliance": "C",
    "timeline": "TL",
    "unclear": "U",
}

# Heuristic regexes (ported from activities/intake.py — keep behaviour parity).
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_MODAL_RE = re.compile(
    r"\b(?:shall|must|should|may|will|need(?:s|ed)?\s+to|is\s+required\s+to)\b",
    re.IGNORECASE,
)
_PRIORITY_HINTS: tuple[tuple[re.Pattern[str], AtomPriority], ...] = (
    (re.compile(r"\b(must|shall|required)\b", re.IGNORECASE), "MUST"),
    (re.compile(r"\bshould\b", re.IGNORECASE), "SHOULD"),
    (re.compile(r"\b(may|could|optional)\b", re.IGNORECASE), "COULD"),
    (re.compile(r"\b(will\s+not|out\s+of\s+scope)\b", re.IGNORECASE), "WONT"),
)
_NFR_HINTS = ("latency", "throughput", "uptime", "availability", "p95", "rto", "rpo")
_COMPLIANCE_HINTS = ("hipaa", "pci", "gdpr", "iso", "sox", "fedramp")
_TIMELINE_HINTS = ("deadline", "by q", "by 20", "milestone", "phase")
_TECH_HINTS = ("rest", "graphql", "grpc", "kubernetes", "docker", "aws", "azure")

# Approximate chunk size — LiteLLM normalises across providers. 8K tokens ≈ 32K chars.
_CHUNK_CHAR_LIMIT = 32_000


class _AtomCandidate(BaseModel):
    """Wire shape returned by the LLM — validated then converted to AtomFrontmatter."""

    id_seq: int = 0
    type: AtomType = "unclear"
    priority: AtomPriority = "SHOULD"
    category: str = "general"
    title: str = ""
    body: str = ""
    section: str | None = None
    page: int | None = None
    line_range: tuple[int, int] | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.6
    split_recommended: bool = False


def _heuristic_priority(text: str) -> AtomPriority:
    for pattern, priority in _PRIORITY_HINTS:
        if pattern.search(text):
            return priority
    return "SHOULD"


def _heuristic_type(text: str) -> AtomType:
    lowered = text.lower()
    if any(h in lowered for h in _COMPLIANCE_HINTS):
        return "compliance"
    if any(h in lowered for h in _NFR_HINTS):
        return "nfr"
    if any(h in lowered for h in _TIMELINE_HINTS):
        return "timeline"
    if any(h in lowered for h in _TECH_HINTS):
        return "technical"
    if _MODAL_RE.search(lowered):
        return "functional"
    return "unclear"


def _heuristic_extract(file: ParsedFile) -> list[_AtomCandidate]:
    """Port of activities/intake._extract_requirements + lightweight typing.

    Returns one candidate per bullet or modal-verb sentence. Confidence flat
    at 0.5 per §8 stub-fallback contract. ``split_recommended`` always False
    on the heuristic path (no priority-mixing detection without LLM).
    """
    raw = file.raw_text or ""
    candidates: list[_AtomCandidate] = []

    # Pass 1: explicit bullets across the file.
    for line in raw.splitlines():
        match = _BULLET_RE.match(line)
        if match:
            text = match.group(1).strip()
            if len(text) < 8:
                continue
            candidates.append(
                _AtomCandidate(
                    type=_heuristic_type(text),
                    priority=_heuristic_priority(text),
                    category="general",
                    title=text[:80],
                    body=text,
                    section=None,
                    confidence=0.5,
                )
            )

    # Pass 2: when no bullets present, fall back to modal-verb sentences.
    if not candidates:
        for sentence in re.split(r"(?<=[.!?])\s+", raw):
            sentence = sentence.strip()
            if len(sentence) < 12 or not _MODAL_RE.search(sentence):
                continue
            candidates.append(
                _AtomCandidate(
                    type=_heuristic_type(sentence),
                    priority=_heuristic_priority(sentence),
                    category="general",
                    title=sentence[:80],
                    body=sentence,
                    confidence=0.5,
                )
            )
            if len(candidates) >= 50:
                break

    return candidates


def _strip_json_fence(text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return cleaned.strip()


def _parse_llm_chunk(text: str) -> list[_AtomCandidate]:
    cleaned = _strip_json_fence(text)
    if not cleaned:
        return []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("atom_extractor.parse_fail err=%s preview=%r", exc, cleaned[:80])
        return []
    if not isinstance(data, list):
        return []
    out: list[_AtomCandidate] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            out.append(_AtomCandidate.model_validate(entry))
        except ValidationError as exc:
            logger.debug("atom_extractor.candidate_invalid err=%s", exc)
    return out


def _split_chunks(text: str, *, limit: int = _CHUNK_CHAR_LIMIT) -> list[str]:
    """Yield chunks of ~``limit`` chars, breaking on paragraph boundaries."""
    if len(text) <= limit:
        return [text] if text.strip() else []
    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + limit, len(text))
        if end < len(text):
            # Walk back to the last paragraph break to keep coherent chunks.
            split = text.rfind("\n\n", cursor + (limit // 2), end)
            if split > cursor:
                end = split
        chunk = text[cursor:end].strip()
        if chunk:
            chunks.append(chunk)
        cursor = end + 2 if end < len(text) and text[end:end + 2] == "\n\n" else end
    return chunks


def _assign_atom_ids(candidates: list[_AtomCandidate]) -> list[tuple[str, _AtomCandidate]]:
    """Return ``[(REQ-<TYPE>-NNN, candidate), ...]`` keyed per-bid uniqueness.

    Per §3.1 / Decision #4: id format ``REQ-<TYPE>-<3-digit-seq>``, scoped to
    one bid (parse_session pre-confirm; bid_id post-confirm).
    """
    counters: dict[str, int] = {}
    out: list[tuple[str, _AtomCandidate]] = []
    for cand in candidates:
        prefix = _TYPE_PREFIX.get(cand.type, "U")
        counters[prefix] = counters.get(prefix, 0) + 1
        atom_id = f"REQ-{prefix}-{counters[prefix]:03d}"
        out.append((atom_id, cand))
    return out


def _candidate_to_atom(
    atom_id: str,
    cand: _AtomCandidate,
    *,
    file: ParsedFile,
    tenant_id: str,
    bid_id: str,
    parser_label: str,
    ai_generated: bool,
) -> tuple[AtomFrontmatter, str]:
    """Convert a candidate + file metadata into ``(AtomFrontmatter, body_md)``."""
    source = AtomSource(
        file=f"sources/{file.file_id}.md",
        section=cand.section,
        page=cand.page,
        line_range=cand.line_range,
    )
    extraction = AtomExtraction(
        parser=parser_label,
        confidence=max(0.0, min(1.0, cand.confidence)),
        extracted_at=utcnow(),
    )
    front = AtomFrontmatter(
        id=atom_id,
        type=cand.type,
        priority=cand.priority,
        category=cand.category or "general",
        source=source,
        extraction=extraction,
        verification=AtomVerification(),
        links=AtomLinks(),
        tags=cand.tags or [],
        tenant_id=tenant_id,
        bid_id=bid_id,
        split_recommended=cand.split_recommended,
        ai_generated=ai_generated,
        approved=False,
    )
    body_md = (cand.body or cand.title).strip() or atom_id
    return (front, body_md)


async def extract_atoms(
    file: ParsedFile,
    *,
    bid_id: str,
    tenant_id: str,
    lang: str = "en",
    client: LLMClient | None = None,
    bid_id_for_trace: str | None = None,
) -> list[tuple[AtomFrontmatter, str]]:
    """Extract atoms from one :class:`ParsedFile`.

    Returns ``[(AtomFrontmatter, body_md), ...]`` ready for atom_emitter
    consumption. Both LLM and stub paths emit valid frontmatter — the stub
    path simply flags ``ai_generated=False`` + ``confidence=0.5`` per §8.
    """
    from config.llm import is_llm_available

    candidates: list[_AtomCandidate] = []
    parser_label: str
    ai_generated: bool

    if not is_llm_available():
        candidates = _heuristic_extract(file)
        parser_label = "heuristic_v1"
        ai_generated = False
        logger.info(
            "atom_extractor.stub_path file=%s atoms=%d",
            file.name,
            len(candidates),
        )
    else:
        prompt = (
            SYSTEM_PROMPT_ATOM_EXTRACTOR_VI
            if (lang == "vi" or file.language == "vi")
            else SYSTEM_PROMPT_ATOM_EXTRACTOR_EN
        )
        conv = LLMConversation(
            system=prompt,
            client=client,
            default_tier=_TIER,
            default_max_tokens=2048,
            default_temperature=0.2,
            trace_id=bid_id_for_trace,
        )
        chunks = _split_chunks(file.raw_text or "")
        if not chunks:
            return []
        for idx, chunk in enumerate(chunks):
            try:
                response = await conv.send(
                    chunk,
                    tier=_TIER,
                    node_name=f"atom_extractor.chunk_{idx}",
                )
            except Exception as exc:  # noqa: BLE001 — degrade per-chunk on failure
                logger.warning(
                    "atom_extractor.chunk_failed file=%s chunk=%d err=%s",
                    file.name,
                    idx,
                    exc,
                )
                continue
            candidates.extend(_parse_llm_chunk(response.text))
        parser_label = "rfp_extractor_v2.1"
        ai_generated = True
        # If LLM returned nothing usable, degrade to heuristic so the bid
        # still has scaffolding for reviewer to start from.
        if not candidates:
            logger.info(
                "atom_extractor.llm_empty_falling_back_to_heuristic file=%s",
                file.name,
            )
            candidates = _heuristic_extract(file)
            parser_label = "heuristic_v1"
            ai_generated = False

    atoms: list[tuple[AtomFrontmatter, str]] = []
    for atom_id, cand in _assign_atom_ids(candidates):
        atoms.append(
            _candidate_to_atom(
                atom_id,
                cand,
                file=file,
                tenant_id=tenant_id,
                bid_id=bid_id,
                parser_label=parser_label,
                ai_generated=ai_generated,
            )
        )
    return atoms


__all__ = ["extract_atoms"]
