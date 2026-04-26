"""S6 WBS agent — single small-tier LLMConversation turn.

Pattern (Phase 2-real / Conv 14):
- LLM tailors the WBS *items* (ids, names, owner roles, dependencies, effort) to
  the BA functional requirements + HLD topology.
- Wrapper recomputes ``total_effort_md`` (sum) and ``timeline_weeks`` (20 MD = 1
  pod-week heuristic) so the artifact's invariants always hold even if the LLM
  drifts on arithmetic.
- Returns the merged :class:`WBSDraft`. On parse / validation failure the caller
  falls back to the deterministic stub.
"""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.wbs_agent import SYSTEM_PROMPT_WBS
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from tools.llm.types import LLMResponse
from workflows.artifacts import WBSDraft, WBSInput, WBSItem

logger = logging.getLogger(__name__)

_TIER = "small"
_MD_PER_POD_WEEK = 20.0  # 5-person pod x 4 working days/week (Phase 2.1 heuristic kept)
_MIN_TIMELINE_WEEKS = 4

# Reference 7-phase template the LLM starts from (matches the legacy stub so the
# fallback artifact stays shape-compatible).
_REFERENCE_TEMPLATE: list[dict] = [
    {"id": "WBS-000", "name": "Project initiation + governance setup",
     "effort_md": 10.0, "owner_role": "pm"},
    {"id": "WBS-100", "name": "Discovery + requirements firm-up",
     "effort_md": 20.0, "owner_role": "ba"},
    {"id": "WBS-200", "name": "Solution design + architecture spikes",
     "effort_md": 25.0, "owner_role": "sa"},
    {"id": "WBS-300", "name": "Core build — MVP scope",
     "effort_md": 80.0, "owner_role": "pm"},
    {"id": "WBS-400", "name": "Integration + data migration",
     "effort_md": 30.0, "owner_role": "sa"},
    {"id": "WBS-500", "name": "Test (SIT + UAT)",
     "effort_md": 25.0, "owner_role": "qc"},
    {"id": "WBS-600", "name": "Cutover + hypercare",
     "effort_md": 15.0, "owner_role": "pm"},
]


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class _WBSLLMOutput(BaseModel):
    """Schema the small-tier model must return — items + critical_path only."""

    items: list[WBSItem] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    rationale: str = ""


def _strip_json(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _build_user_payload(payload: WBSInput) -> str:
    ba = payload.ba_draft
    must_count = sum(1 for fr in ba.functional_requirements if fr.priority == "MUST")
    hld = payload.hld
    hld_summary = (
        None
        if hld is None
        else {
            "components": [c.name for c in hld.components],
            "integration_points": list(hld.integration_points),
            "deployment_model": hld.deployment_model,
        }
    )
    return json.dumps(
        {
            "bid_id": str(payload.bid_id),
            "ba": {
                "must_count": must_count,
                "executive_summary": ba.executive_summary[:600],
                "key_functional": [
                    {"id": fr.id, "title": fr.title, "priority": fr.priority}
                    for fr in ba.functional_requirements[:10]
                ],
                "risks": [r.title for r in ba.risks[:5]],
            },
            "hld": hld_summary,
            "reference_template": _REFERENCE_TEMPLATE,
        },
        ensure_ascii=False,
    )


def _validate_dependencies(items: list[WBSItem]) -> list[WBSItem]:
    """Strip any depends_on entry that references an unknown id (defensive)."""
    known_ids = {it.id for it in items}
    cleaned: list[WBSItem] = []
    for it in items:
        if it.depends_on:
            it.depends_on = [d for d in it.depends_on if d in known_ids]
        cleaned.append(it)
    return cleaned


def _finalise_wbs(
    bid_id: UUID,
    parsed: _WBSLLMOutput,
    response: LLMResponse,
    cost_usd: float,
) -> WBSDraft:
    items = _validate_dependencies(list(parsed.items))
    if not items:
        raise ValueError("LLM returned empty WBS items")
    total = round(sum(it.effort_md for it in items), 1)
    timeline_weeks = max(_MIN_TIMELINE_WEEKS, int(round(total / _MD_PER_POD_WEEK)))
    known_ids = {it.id for it in items}
    critical_path = [c for c in parsed.critical_path if c in known_ids]
    return WBSDraft(
        bid_id=bid_id,
        items=items,
        total_effort_md=total,
        timeline_weeks=timeline_weeks,
        critical_path=critical_path,
        llm_cost_usd=round(cost_usd, 6),
        llm_tier_used=_TIER,
    )


async def run_wbs_agent(
    payload: WBSInput,
    *,
    client: LLMClient | None = None,
) -> WBSDraft:
    """Run the small-tier WBS turn; raise on unrecoverable parse error."""
    conv = LLMConversation(
        system=SYSTEM_PROMPT_WBS,
        client=client,
        default_tier=_TIER,
        default_max_tokens=2048,
        default_temperature=0.2,
        trace_id=str(payload.bid_id),
    )
    response = await conv.send(
        _build_user_payload(payload),
        tier=_TIER,
        node_name="wbs_agent.synthesise",
    )
    try:
        parsed = _WBSLLMOutput.model_validate_json(_strip_json(response.text))
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "wbs_agent.parse_fail bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        raise
    draft = _finalise_wbs(payload.bid_id, parsed, response, conv.total_cost_usd)
    logger.info(
        "wbs_agent.done bid_id=%s items=%d total_md=%.1f weeks=%d cost_usd=%.6f",
        payload.bid_id,
        len(draft.items),
        draft.total_effort_md,
        draft.timeline_weeks,
        draft.llm_cost_usd or 0.0,
    )
    return draft


__all__ = ["run_wbs_agent", "_REFERENCE_TEMPLATE"]
