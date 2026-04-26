"""S5 Solution Design agent — flagship synth + small critique LLMConversation.

Pattern (Phase 2-real / Conv 14):
- Turn 1 (flagship): drafts the HLD JSON (architecture overview + components +
  data_flows + integration_points + security_approach + deployment_model).
- Turn 2 (small): critiques the draft. Wrapper patches the draft when the
  critique surfaces concrete gaps (SA `integrations` not carried over, missing
  security gaps, etc.) and bumps confidence into the artifact's notes.
- Single :class:`LLMConversation` keeps both turns under one trace_id; cost
  rolls up across both turns.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.solution_design_agent import (
    SYSTEM_PROMPT_HLD,
    SYSTEM_PROMPT_HLD_CRITIQUE,
)
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.artifacts import (
    HLDComponent,
    HLDDraft,
    SolutionDesignInput,
)

logger = logging.getLogger(__name__)

_DRAFT_TIER = "flagship"
_CRITIQUE_TIER = "small"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class _HLDLLMOutput(BaseModel):
    architecture_overview: str
    components: list[HLDComponent] = Field(default_factory=list)
    data_flows: list[str] = Field(default_factory=list)
    integration_points: list[str] = Field(default_factory=list)
    security_approach: str = ""
    deployment_model: str = ""


class _HLDCritiqueOutput(BaseModel):
    missing_components: list[str] = Field(default_factory=list)
    weak_data_flows: list[str] = Field(default_factory=list)
    security_gaps: list[str] = Field(default_factory=list)
    deployment_gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


def _strip_json(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _build_draft_payload(payload: SolutionDesignInput) -> str:
    sa = payload.sa_draft
    return json.dumps(
        {
            "bid_id": str(payload.bid_id),
            "convergence": {
                "unified_summary": payload.convergence.unified_summary[:1200],
                "open_questions": list(payload.convergence.open_questions[:5]),
                "readiness": dict(payload.convergence.readiness),
            },
            "sa": {
                "tech_stack": [
                    {"layer": t.layer, "choice": t.choice, "rationale": t.rationale}
                    for t in sa.tech_stack
                ],
                "architecture_patterns": [
                    {"name": p.name, "description": p.description}
                    for p in sa.architecture_patterns
                ],
                "integrations": list(sa.integrations),
                "nfr_targets": dict(sa.nfr_targets),
                "technical_risks": [
                    {"title": r.title, "likelihood": r.likelihood,
                     "impact": r.impact, "mitigation": r.mitigation}
                    for r in sa.technical_risks
                ],
            },
        },
        ensure_ascii=False,
    )


def _build_critique_payload(
    payload: SolutionDesignInput, draft_json: dict[str, Any]
) -> str:
    return json.dumps(
        {
            "draft": draft_json,
            "sa_integrations": list(payload.sa_draft.integrations),
            "sa_tech_stack_layers": [t.layer for t in payload.sa_draft.tech_stack],
        },
        ensure_ascii=False,
    )


def _validate_dependencies(components: list[HLDComponent]) -> list[HLDComponent]:
    """Strip dangling depends_on references."""
    known = {c.name for c in components}
    for c in components:
        c.depends_on = [d for d in c.depends_on if d in known]
    return components


def _merge_critique(
    draft: _HLDLLMOutput,
    critique: _HLDCritiqueOutput,
    sa_integrations: list[str],
) -> _HLDLLMOutput:
    """Patch the draft with critique findings the wrapper can apply deterministically."""
    # Carry over any SA integration the LLM dropped.
    existing = {ip.lower() for ip in draft.integration_points}
    for ip in sa_integrations:
        if ip and ip.lower() not in existing:
            draft.integration_points.append(ip)
            existing.add(ip.lower())

    # Append security / deployment gap notes so the human reviewer sees them.
    if critique.security_gaps:
        draft.security_approach = (
            (draft.security_approach + " ").strip()
            + " Open gaps flagged by critique: "
            + "; ".join(critique.security_gaps)
        )
    if critique.deployment_gaps:
        draft.deployment_model = (
            (draft.deployment_model + " ").strip()
            + " Deployment gaps flagged: "
            + "; ".join(critique.deployment_gaps)
        )
    if critique.weak_data_flows:
        # surface weak flows so they're at least visible in the artifact
        for flow in critique.weak_data_flows:
            note = f"⚠ critique-flagged: {flow}"
            if note not in draft.data_flows:
                draft.data_flows.append(note)
    return draft


def _finalise_hld(
    bid_id: UUID,
    draft: _HLDLLMOutput,
    critique: _HLDCritiqueOutput,
    cost_usd: float,
) -> HLDDraft:
    components = _validate_dependencies(list(draft.components))
    if not components:
        raise ValueError("LLM returned empty HLD components")
    return HLDDraft(
        bid_id=bid_id,
        architecture_overview=draft.architecture_overview,
        components=components,
        data_flows=draft.data_flows,
        integration_points=draft.integration_points,
        security_approach=draft.security_approach,
        deployment_model=draft.deployment_model,
        llm_cost_usd=round(cost_usd, 6),
        llm_tier_used=f"{_DRAFT_TIER}+{_CRITIQUE_TIER}",
    )


async def run_solution_design_agent(
    payload: SolutionDesignInput,
    *,
    client: LLMClient | None = None,
) -> HLDDraft:
    """Two-turn LLMConversation: flagship draft → small critique → merged HLD."""
    conv = LLMConversation(
        system=SYSTEM_PROMPT_HLD,
        client=client,
        default_tier=_DRAFT_TIER,
        default_max_tokens=3072,
        default_temperature=0.2,
        trace_id=str(payload.bid_id),
    )

    draft_response = await conv.send(
        _build_draft_payload(payload),
        tier=_DRAFT_TIER,
        node_name="solution_design.draft",
    )
    try:
        draft_parsed = _HLDLLMOutput.model_validate_json(_strip_json(draft_response.text))
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "solution_design.draft_parse_fail bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        raise

    # Critique turn — swap system to the critique prompt by re-seeding.
    # LLMConversation locks `system` at construction; re-prompt via user message.
    critique_response = await conv.send(
        f"INSTRUCTION SWITCH — apply this system role for THIS turn only:\n"
        f"{SYSTEM_PROMPT_HLD_CRITIQUE}\n\n"
        f"INPUT:\n{_build_critique_payload(payload, draft_parsed.model_dump())}",
        tier=_CRITIQUE_TIER,
        max_tokens=1024,
        temperature=0.0,
        node_name="solution_design.critique",
    )
    try:
        critique_parsed = _HLDCritiqueOutput.model_validate_json(
            _strip_json(critique_response.text)
        )
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "solution_design.critique_parse_fail bid_id=%s err=%s — using draft as-is",
            payload.bid_id,
            exc,
        )
        critique_parsed = _HLDCritiqueOutput()  # default — draft unchanged

    merged = _merge_critique(
        draft_parsed,
        critique_parsed,
        list(payload.sa_draft.integrations),
    )
    hld = _finalise_hld(payload.bid_id, merged, critique_parsed, conv.total_cost_usd)
    logger.info(
        "solution_design.done bid_id=%s components=%d integrations=%d "
        "critique_confidence=%.2f cost_usd=%.6f",
        payload.bid_id,
        len(hld.components),
        len(hld.integration_points),
        critique_parsed.confidence,
        hld.llm_cost_usd or 0.0,
    )
    return hld


__all__ = ["run_solution_design_agent"]
