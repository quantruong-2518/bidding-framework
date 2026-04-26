"""S11 Retrospective agent — single flagship-tier LLMConversation turn.

Pattern (Conv 15):
- LLM reflects across every populated phase artifact and returns ``lessons`` +
  structured ``kb_deltas`` (the latter are what the wrapper persists to
  ``kb-vault/lessons/`` with ``ai_generated: true`` frontmatter).
- Stub-fallback contract preserved: parse / empty failure raises so the
  activity wrapper picks the deterministic stub.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.retrospective_agent import SYSTEM_PROMPT_RETROSPECTIVE
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.artifacts import (
    KBDelta,
    Lesson,
    RetrospectiveDraft,
    RetrospectiveInput,
)

logger = logging.getLogger(__name__)

_TIER = "flagship"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class _RetroLLMOutput(BaseModel):
    outcome: str = "PENDING"
    lessons: list[Lesson] = Field(default_factory=list)
    kb_deltas: list[KBDelta] = Field(default_factory=list)


def _strip_json(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _coerce_outcome(raw: str) -> str:
    candidate = (raw or "").strip().upper()
    return candidate if candidate in {"WIN", "LOSS", "PENDING"} else "PENDING"


def _build_user_payload(payload: RetrospectiveInput) -> str:
    """Assemble the JSON context the LLM reflects on. Every section is optional."""
    sub = payload.submission
    blob: dict[str, Any] = {
        "bid_id": str(payload.bid_id),
        "client_name": payload.client_name,
        "industry": payload.industry,
        "submission": {
            "channel": sub.channel,
            "submitted_at": sub.submitted_at.isoformat(),
            "confirmation_id": sub.confirmation_id,
            "checklist": dict(sub.checklist),
        },
    }
    if payload.ba_draft is not None:
        blob["ba"] = {
            "executive_summary": payload.ba_draft.executive_summary[:600],
            "must_count": sum(
                1 for fr in payload.ba_draft.functional_requirements if fr.priority == "MUST"
            ),
            "risks": [r.title for r in payload.ba_draft.risks[:5]],
        }
    if payload.sa_draft is not None:
        blob["sa"] = {
            "tech_stack": [
                {"layer": t.layer, "choice": t.choice} for t in payload.sa_draft.tech_stack
            ],
            "technical_risks": [r.title for r in payload.sa_draft.technical_risks[:5]],
        }
    if payload.domain_notes is not None:
        blob["domain"] = {
            "compliance": [
                {"framework": c.framework, "applies": c.applies}
                for c in payload.domain_notes.compliance
            ],
            "best_practices": [p.title for p in payload.domain_notes.best_practices[:5]],
        }
    if payload.convergence is not None:
        blob["convergence"] = {
            "readiness": dict(payload.convergence.readiness),
            "conflict_count": len(payload.convergence.conflicts),
            "open_questions": list(payload.convergence.open_questions[:5]),
        }
    if payload.wbs is not None:
        blob["wbs"] = {
            "total_effort_md": payload.wbs.total_effort_md,
            "timeline_weeks": payload.wbs.timeline_weeks,
            "critical_path": list(payload.wbs.critical_path),
        }
    if payload.pricing is not None:
        blob["pricing"] = {
            "total": payload.pricing.total,
            "margin_pct": payload.pricing.margin_pct,
            "model": payload.pricing.model,
        }
    if payload.reviews:
        blob["reviews"] = [
            {"verdict": r.verdict, "comment_count": len(r.comments)}
            for r in payload.reviews
        ]
    return json.dumps(blob, ensure_ascii=False)


def _normalise_kb_deltas(
    bid_id: UUID, deltas: list[KBDelta]
) -> list[KBDelta]:
    """Force unique ids + vault-relative target paths under ``lessons/``."""
    seen_ids: set[str] = set()
    cleaned: list[KBDelta] = []
    for idx, raw in enumerate(deltas):
        delta_id = raw.id if raw.id and raw.id not in seen_ids else f"DELTA-{idx + 1:03d}"
        seen_ids.add(delta_id)
        # Always rewrite target_path so the wrapper-side sandbox is enforced.
        target = f"lessons/{bid_id}-{delta_id}.md"
        cleaned.append(
            raw.model_copy(
                update={
                    "id": delta_id,
                    "target_path": target,
                    "ai_generated": True,
                    # Approval is a future-conv concern; never trust the LLM to set it.
                    "approved": False,
                }
            )
        )
    return cleaned


def _finalise_retrospective(
    payload: RetrospectiveInput,
    parsed: _RetroLLMOutput,
    cost_usd: float,
) -> RetrospectiveDraft:
    if not parsed.lessons:
        raise ValueError("LLM returned empty lessons list")
    deltas = _normalise_kb_deltas(payload.bid_id, list(parsed.kb_deltas))
    return RetrospectiveDraft(
        bid_id=payload.bid_id,
        outcome=_coerce_outcome(parsed.outcome),  # type: ignore[arg-type]
        lessons=list(parsed.lessons),
        kb_updates=[d.target_path for d in deltas],  # legacy mirror
        kb_deltas=deltas,
        llm_cost_usd=round(cost_usd, 6),
        llm_tier_used=_TIER,
    )


async def run_retrospective_agent(
    payload: RetrospectiveInput,
    *,
    client: LLMClient | None = None,
) -> RetrospectiveDraft:
    """Run the flagship-tier retrospective; raise on unrecoverable parse error."""
    conv = LLMConversation(
        system=SYSTEM_PROMPT_RETROSPECTIVE,
        client=client,
        default_tier=_TIER,
        default_max_tokens=3072,
        default_temperature=0.3,
        trace_id=str(payload.bid_id),
    )
    response = await conv.send(
        _build_user_payload(payload),
        tier=_TIER,
        node_name="retrospective_agent.synthesise",
    )
    try:
        parsed = _RetroLLMOutput.model_validate_json(_strip_json(response.text))
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "retrospective_agent.parse_fail bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        raise
    draft = _finalise_retrospective(payload, parsed, conv.total_cost_usd)
    logger.info(
        "retrospective_agent.done bid_id=%s lessons=%d kb_deltas=%d outcome=%s cost_usd=%.6f",
        payload.bid_id,
        len(draft.lessons),
        len(draft.kb_deltas),
        draft.outcome,
        draft.llm_cost_usd or 0.0,
    )
    return draft


__all__ = ["run_retrospective_agent"]
