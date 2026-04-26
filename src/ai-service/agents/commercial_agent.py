"""S7 Commercial agent — single nano-tier LLMConversation turn.

Pattern (Phase 2-real / Conv 14):
- LLM produces a *commercial narrative* (line items + margin % + advisory notes)
  given WBS totals + industry context.
- Arithmetic (subtotal, total, scenario figures) is computed deterministically in
  the activity wrapper because LLMs are unreliable at multi-step math.
- Returns the merged :class:`PricingDraft`. On parse / validation failure the
  caller falls back to the deterministic stub.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from agents.prompts.commercial_agent import SYSTEM_PROMPT_PRICING
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from tools.llm.types import LLMResponse
from workflows.artifacts import CommercialInput, PricingDraft, PricingLine

logger = logging.getLogger(__name__)

_TIER = "nano"
_BLENDED_DAY_RATE_USD = 900.0  # Same baseline the stub uses; the LLM may adapt around it.

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class _PricingLLMOutput(BaseModel):
    """Schema the nano model must return — narrative only, no arithmetic."""

    model: str = "fixed_price"
    currency: str = "USD"
    lines: list[PricingLine] = Field(default_factory=list)
    margin_pct: float = Field(ge=0.0, le=40.0, default=15.0)
    notes: str = ""


def _strip_json(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _build_user_payload(payload: CommercialInput) -> str:
    return json.dumps(
        {
            "bid_id": str(payload.bid_id),
            "industry": payload.industry,
            "wbs": {
                "total_effort_md": payload.wbs.total_effort_md,
                "timeline_weeks": payload.wbs.timeline_weeks,
                "critical_path": list(payload.wbs.critical_path),
            },
            "baseline_day_rate_usd": _BLENDED_DAY_RATE_USD,
        },
        ensure_ascii=False,
    )


def _coerce_model(raw_model: str) -> str:
    """Snap to the Literal accepted by PricingDraft.model; default to fixed_price."""
    candidate = (raw_model or "").strip().lower()
    if candidate in {"fixed_price", "time_and_materials", "hybrid"}:
        return candidate
    return "fixed_price"


def _finalise_pricing(
    bid_id: UUID,
    parsed: _PricingLLMOutput,
    response: LLMResponse,
    cost_usd: float,
) -> PricingDraft:
    """Apply deterministic arithmetic + scenarios on top of the LLM's narrative."""
    lines = list(parsed.lines)
    if not lines:
        raise ValueError("LLM returned empty pricing lines")
    subtotal = round(sum(line.amount for line in lines), 2)
    margin_pct = float(parsed.margin_pct)
    total = round(subtotal * (1 + margin_pct / 100.0), 2)
    scenarios = {
        "aggressive": round(total * 0.92, 2),
        "baseline": total,
        "conservative": round(total * 1.08, 2),
    }
    return PricingDraft(
        bid_id=bid_id,
        model=_coerce_model(parsed.model),  # type: ignore[arg-type]
        currency=parsed.currency or "USD",
        lines=lines,
        subtotal=subtotal,
        margin_pct=margin_pct,
        total=total,
        scenarios=scenarios,
        notes=parsed.notes or "Advisory only — commercial team adjusts before S8 assembly.",
        llm_cost_usd=round(cost_usd, 6),
        llm_tier_used=_TIER,
    )


async def run_commercial_agent(
    payload: CommercialInput,
    *,
    client: LLMClient | None = None,
) -> PricingDraft:
    """Run the nano-tier pricing turn; raise on unrecoverable parse error.

    Callers (typically the activity wrapper) catch the exception and fall back
    to the deterministic stub. The exception type is intentionally broad so
    JSON / pydantic / value errors all funnel through the same fallback path.
    """
    conv = LLMConversation(
        system=SYSTEM_PROMPT_PRICING,
        client=client,
        default_tier=_TIER,
        default_max_tokens=1024,
        default_temperature=0.2,
        trace_id=str(payload.bid_id),
    )
    response = await conv.send(
        _build_user_payload(payload),
        tier=_TIER,
        node_name="commercial_agent.pricing",
    )
    try:
        parsed = _PricingLLMOutput.model_validate_json(_strip_json(response.text))
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "commercial_agent.parse_fail bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        raise
    draft = _finalise_pricing(payload.bid_id, parsed, response, conv.total_cost_usd)
    logger.info(
        "commercial_agent.done bid_id=%s lines=%d total=%.2f tier=%s cost_usd=%.6f",
        payload.bid_id,
        len(draft.lines),
        draft.total,
        _TIER,
        draft.llm_cost_usd or 0.0,
    )
    return draft


# Re-export so test fixtures can introspect what the agent considers
# "the deterministic baseline rate" without importing the activity stub.
__all__ = ["run_commercial_agent", "_BLENDED_DAY_RATE_USD"]
_ = Any  # keep ``Any`` reachable for type-narrowed extensions
