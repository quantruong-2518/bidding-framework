"""S4 semantic-compare agent — single small-tier LLMConversation turn.

Pattern (Conv 15):
- Augment, NOT replace, the deterministic R1/R2/R3 heuristics in
  ``activities.convergence``. The wrapper merges the agent's conflicts into the
  existing list and dedupes by ``topic`` so a heuristic + LLM both flagging the
  same issue land as a single conflict (heuristic version wins on tie).
- On parse failure the wrapper returns ``[]`` so the caller silently falls
  back to the heuristic-only conflict list.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.convergence_agent import SYSTEM_PROMPT_SEMANTIC_COMPARE
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.artifacts import (
    BusinessRequirementsDraft,
    DomainNotes,
    SolutionArchitectureDraft,
    StreamConflict,
)

logger = logging.getLogger(__name__)

_TIER = "small"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class _SemanticCompareOutput(BaseModel):
    conflicts: list[StreamConflict] = Field(default_factory=list)


def _strip_json(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _build_user_payload(
    ba: BusinessRequirementsDraft,
    sa: SolutionArchitectureDraft,
    domain: DomainNotes,
    existing: list[StreamConflict],
) -> str:
    return json.dumps(
        {
            "ba": {
                "executive_summary": ba.executive_summary[:600],
                "in_scope": list(ba.scope.get("in_scope", []))[:10],
                "success_criteria": list(ba.success_criteria[:8]),
            },
            "sa": {
                "tech_stack": [
                    {"layer": t.layer, "choice": t.choice, "rationale": t.rationale[:200]}
                    for t in sa.tech_stack
                ],
                "nfr_targets": dict(sa.nfr_targets),
                "integrations": list(sa.integrations),
                "technical_risks": [r.title for r in sa.technical_risks[:5]],
            },
            "domain": {
                "compliance": [
                    {"framework": c.framework, "applies": c.applies}
                    for c in domain.compliance
                ],
                "best_practices": [p.title for p in domain.best_practices[:5]],
            },
            "existing_conflict_topics": [c.topic for c in existing],
        },
        ensure_ascii=False,
    )


async def run_semantic_compare(
    ba: BusinessRequirementsDraft,
    sa: SolutionArchitectureDraft,
    domain: DomainNotes,
    existing: list[StreamConflict],
    *,
    bid_id_for_trace: str,
    client: LLMClient | None = None,
) -> tuple[list[StreamConflict], float]:
    """Run the small-tier semantic compare; returns (new_conflicts, cost_usd).

    On any failure (parse, schema, exception) returns ``([], 0.0)`` so callers
    silently fall back to heuristic-only output. The activity wrapper logs.
    """
    conv = LLMConversation(
        system=SYSTEM_PROMPT_SEMANTIC_COMPARE,
        client=client,
        default_tier=_TIER,
        default_max_tokens=1024,
        default_temperature=0.2,
        trace_id=bid_id_for_trace,
    )
    try:
        response = await conv.send(
            _build_user_payload(ba, sa, domain, existing),
            tier=_TIER,
            node_name="convergence_agent.semantic_compare",
        )
    except Exception as exc:  # noqa: BLE001 — never break convergence on LLM glitch
        logger.warning("convergence_agent.send_failed err=%s", exc)
        return ([], 0.0)

    try:
        parsed = _SemanticCompareOutput.model_validate_json(_strip_json(response.text))
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("convergence_agent.parse_fail err=%s", exc)
        return ([], conv.total_cost_usd)

    # Drop topics that already exist in the heuristic list (case-insensitive).
    existing_topics = {c.topic.lower() for c in existing}
    fresh = [c for c in parsed.conflicts if c.topic.lower() not in existing_topics]
    logger.info(
        "convergence_agent.done new_conflicts=%d (raw=%d, deduped=%d) cost_usd=%.6f",
        len(fresh),
        len(parsed.conflicts),
        len(parsed.conflicts) - len(fresh),
        conv.total_cost_usd,
    )
    return (fresh, conv.total_cost_usd)


__all__ = ["run_semantic_compare"]
