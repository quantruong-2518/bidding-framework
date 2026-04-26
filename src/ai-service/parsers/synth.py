"""S0.5 synth — produce anchor + executive summary + open_questions.

LLM path: 2-turn :class:`LLMConversation`. First turn at flagship tier
synthesises ``{anchor_md, summary_md, open_questions}``; second turn at
small tier critiques the draft and surfaces additional questions the
wrapper merges into ``open_questions``.

Stub path: template-based concat keyed off the BidCardSuggestion + atom
distribution. Anchor + summary still under 1.5K and 2.5K tokens
respectively per §8.

Returns :class:`SynthOutput` so context_synthesis activity can pin the
output into the parse_sessions row pre-confirm OR materialise to vault
post-confirm.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.synth import (
    SYSTEM_PROMPT_SYNTH_CRITIQUE_EN,
    SYSTEM_PROMPT_SYNTH_CRITIQUE_VI,
    SYSTEM_PROMPT_SYNTH_EN,
    SYSTEM_PROMPT_SYNTH_VI,
)
from parsers.models import BidCardSuggestion
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.base import AtomFrontmatter, ParsedFile

logger = logging.getLogger(__name__)

_FLAGSHIP = "flagship"
_SMALL = "small"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class SynthOutput(BaseModel):
    """Wire shape returned by :func:`synthesize_context`."""

    anchor_md: str = ""
    summary_md: str = ""
    open_questions: list[str] = Field(default_factory=list)


class _CritiqueOutput(BaseModel):
    gaps: list[str] = Field(default_factory=list)
    factual_concerns: list[str] = Field(default_factory=list)
    additional_questions: list[str] = Field(default_factory=list)
    overall_confidence: float = 0.5


def _strip_fence(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _atom_summary(atoms: list[tuple[AtomFrontmatter, str]]) -> dict[str, Any]:
    """Compact atom statistics for the LLM user turn."""
    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    titles: list[str] = []
    for front, body in atoms:
        by_type[front.type] = by_type.get(front.type, 0) + 1
        by_priority[front.priority] = by_priority.get(front.priority, 0) + 1
        # Body's first line is the natural "title" surface for the synth call.
        first_line = body.splitlines()[0].strip() if body else front.id
        titles.append(f"{front.id}: {first_line[:80]}")
    return {
        "total": len(atoms),
        "by_type": by_type,
        "by_priority": by_priority,
        "top_titles": titles[:10],
    }


def _file_summary(files: list[ParsedFile]) -> list[dict[str, Any]]:
    return [
        {
            "file_id": f.file_id,
            "name": f.name,
            "role": f.role,
            "language": f.language,
            "page_count": f.page_count,
            "size_bytes": f.size_bytes,
        }
        for f in files
    ]


def _stub_anchor(bid_card: BidCardSuggestion, atoms_summary: dict[str, Any]) -> str:
    """Template-based fallback when the LLM is unavailable.

    Tracks the schema the real LLM emits — frontend doesn't need to switch
    code paths. Capped at ~600 chars so it stays inside the 800-token bound.
    """
    lines = [
        f"# Project Context — {bid_card.client_name or 'Unknown Client'}",
        "",
        "## Opportunity framing",
        "",
        f"- Industry: {bid_card.industry or 'unspecified'}",
        f"- Region: {bid_card.region or 'unspecified'}",
        f"- Estimated profile: {bid_card.estimated_profile_hint or 'unknown'}",
        "",
        "## Scope summary",
        "",
        (bid_card.scope_summary or "Scope details to be confirmed by reviewer.")[:500],
        "",
        "## Atom distribution",
        "",
        f"- Total atoms: {atoms_summary['total']}",
        f"- By priority: {atoms_summary['by_priority']}",
        f"- By type: {atoms_summary['by_type']}",
    ]
    return "\n".join(lines)


def _stub_summary(
    bid_card: BidCardSuggestion,
    files: list[ParsedFile],
    atoms_summary: dict[str, Any],
) -> str:
    """Template-based fallback for the executive summary."""
    file_names = ", ".join(f.name for f in files) or "(no files)"
    lines = [
        f"# Executive summary — {bid_card.client_name or 'Unknown Client'}",
        "",
        "## Background",
        "",
        bid_card.scope_summary or "No scope summary detected.",
        "",
        "## Files received",
        "",
        f"- {len(files)} files: {file_names}",
        "",
        "## Atom mix",
        "",
        f"- Total: {atoms_summary['total']}",
        f"- Functional: {atoms_summary['by_type'].get('functional', 0)}",
        f"- NFR: {atoms_summary['by_type'].get('nfr', 0)}",
        f"- Compliance: {atoms_summary['by_type'].get('compliance', 0)}",
        "",
        "## Reviewer next steps",
        "",
        "1. Validate scope summary + estimated profile.",
        "2. Confirm atom priorities (especially MUSTs).",
        "3. Resolve open_questions before workflow start.",
    ]
    return "\n".join(lines)


def _stub_open_questions(
    atoms: list[tuple[AtomFrontmatter, str]],
    files: list[ParsedFile],
) -> list[str]:
    """Aggregate unclear / low-confidence atoms into open questions."""
    questions: list[str] = []
    for front, body in atoms:
        if front.type == "unclear" or front.extraction.confidence < 0.6:
            first_line = body.splitlines()[0].strip() if body else front.id
            questions.append(
                f"Confirm requirement {front.id}: {first_line[:120]}"
            )
        if len(questions) >= 8:
            break
    if not files:
        questions.append("No files were attached to this parse session.")
    elif not any(f.role == "rfp" for f in files):
        questions.append(
            "No file was classified as the primary RFP — review classifications."
        )
    return questions


async def synthesize_context(
    files: list[ParsedFile],
    atoms: list[tuple[AtomFrontmatter, str]],
    bid_card: BidCardSuggestion,
    *,
    lang: str = "en",
    client: LLMClient | None = None,
    bid_id_for_trace: str | None = None,
) -> SynthOutput:
    """Produce ``SynthOutput`` from parsed files + extracted atoms + bid suggestion.

    Behaviour:
      * Stub path when no LLM key — template concat across all three fields.
      * LLM path — 2-turn flagship synth + small critique. Critique gaps land
        as additional open_questions (deduped against synth output).
    """
    from config.llm import is_llm_available

    atoms_summary = _atom_summary(atoms)
    file_meta = _file_summary(files)

    if not is_llm_available():
        anchor = _stub_anchor(bid_card, atoms_summary)
        summary = _stub_summary(bid_card, files, atoms_summary)
        questions = _stub_open_questions(atoms, files)
        return SynthOutput(
            anchor_md=anchor, summary_md=summary, open_questions=questions
        )

    synth_prompt = SYSTEM_PROMPT_SYNTH_VI if lang == "vi" else SYSTEM_PROMPT_SYNTH_EN
    critique_prompt = (
        SYSTEM_PROMPT_SYNTH_CRITIQUE_VI
        if lang == "vi"
        else SYSTEM_PROMPT_SYNTH_CRITIQUE_EN
    )

    user_payload = json.dumps(
        {
            "bid_card": bid_card.model_dump(),
            "atom_summary": atoms_summary,
            "file_summary": file_meta,
        },
        ensure_ascii=False,
    )

    conv = LLMConversation(
        system=synth_prompt,
        client=client,
        default_tier=_FLAGSHIP,
        default_max_tokens=4096,
        default_temperature=0.3,
        trace_id=bid_id_for_trace,
    )

    try:
        synth_response = await conv.send(
            user_payload, tier=_FLAGSHIP, node_name="synth.compose"
        )
    except Exception as exc:  # noqa: BLE001 — degrade to stub
        logger.warning("synth.compose_failed err=%s", exc)
        anchor = _stub_anchor(bid_card, atoms_summary)
        summary = _stub_summary(bid_card, files, atoms_summary)
        questions = _stub_open_questions(atoms, files)
        return SynthOutput(
            anchor_md=anchor, summary_md=summary, open_questions=questions
        )

    try:
        synth_data = json.loads(_strip_fence(synth_response.text))
        synth_out = SynthOutput.model_validate(synth_data)
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("synth.parse_failed err=%s preview=%r", exc, synth_response.text[:80])
        anchor = _stub_anchor(bid_card, atoms_summary)
        summary = _stub_summary(bid_card, files, atoms_summary)
        questions = _stub_open_questions(atoms, files)
        return SynthOutput(
            anchor_md=anchor, summary_md=summary, open_questions=questions
        )

    # ---- Second turn: critique ----------------------------------------------
    # Re-uses same conversation so the model sees its prior draft. The prompt
    # is swapped via ``system`` content of the next turn — but LLMConversation
    # holds system in messages[0]; for the critique we issue a follow-up user
    # turn with the critique-prompt embedded as instructions inline.
    critique_user = (
        f"{critique_prompt}\n\n"
        "Earlier draft (verbatim):\n"
        f"{synth_response.text}"
    )
    try:
        critique_response = await conv.send(
            critique_user, tier=_SMALL, node_name="synth.critique"
        )
        critique_data = json.loads(_strip_fence(critique_response.text))
        critique_out = _CritiqueOutput.model_validate(critique_data)
    except (Exception, ValidationError) as exc:  # noqa: BLE001
        logger.warning("synth.critique_failed err=%s", exc)
        critique_out = _CritiqueOutput()

    # Merge critique additional_questions, preserving order + de-dup.
    seen = set(synth_out.open_questions)
    merged: list[str] = list(synth_out.open_questions)
    for question in critique_out.additional_questions:
        if question not in seen:
            seen.add(question)
            merged.append(question)
    return SynthOutput(
        anchor_md=synth_out.anchor_md,
        summary_md=synth_out.summary_md,
        open_questions=merged,
    )


__all__ = ["synthesize_context", "SynthOutput"]
