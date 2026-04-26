"""S11 Retrospective activity — Temporal wrapper around the retrospective agent.

Falls back to the Phase 2.1 deterministic stub when no LLM provider is
available or when the agent produces unparseable output. After a successful
agent run the wrapper persists each ``KBDelta`` into the Obsidian vault
(``kb-vault/lessons/<bid_id>-<delta_id>.md`` with ``ai_generated: true``
frontmatter) — this is the Conv 15 bi-directional KB sync hook.

The vault write is best-effort: any failure is logged but does NOT break the
workflow, so a vault outage never blocks a bid from completing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from temporalio import activity

from agents.retrospective_agent import run_retrospective_agent
from config.llm import is_llm_available
from kb_writer.kb_delta import write_kb_deltas
from tools.langfuse_client import get_tracer, span_context as langfuse_span_context
from workflows.artifacts import (
    Lesson,
    RetrospectiveDraft,
    RetrospectiveInput,
)

logger = logging.getLogger(__name__)


def _retrospective_stub(payload: RetrospectiveInput) -> RetrospectiveDraft:
    """Phase 2.1 deterministic baseline — preserved as the fallback contract."""
    checklist = payload.submission.checklist
    lessons = [
        Lesson(
            title="Cross-stream readiness baseline",
            category="process",
            detail="Record readiness at S4 convergence to benchmark future bids.",
        ),
        Lesson(
            title="Effort vs estimate delta",
            category="estimation",
            detail="After delivery, compare WBS estimates to actuals to tune the model.",
        ),
    ]
    if not checklist.get("consistency_checks_passed", False):
        lessons.append(
            Lesson(
                title="Assembly consistency gaps",
                category="process",
                detail="Submission passed with consistency warnings — tighten S8 checks.",
            )
        )
    return RetrospectiveDraft(
        bid_id=payload.bid_id,
        outcome="PENDING",
        lessons=lessons,
        kb_updates=[f"retrospective/{payload.bid_id}.md"],
    )


def _resolve_vault_root() -> Path | None:
    """Best-effort vault root resolver. Returns None when the env isn't set."""
    raw = os.environ.get("KB_VAULT_PATH")
    if not raw:
        return None
    return Path(raw).expanduser()


def _persist_kb_deltas(draft: RetrospectiveDraft) -> None:
    """Write KBDeltas to Obsidian; swallow + log every error (best-effort)."""
    if not draft.kb_deltas:
        return
    vault_root = _resolve_vault_root()
    if vault_root is None:
        activity.logger.info(
            "retrospective.kb_writeback_skipped reason=KB_VAULT_PATH_unset bid_id=%s",
            draft.bid_id,
        )
        return
    try:
        receipt = write_kb_deltas(vault_root, draft.bid_id, draft.kb_deltas)
        activity.logger.info(
            "retrospective.kb_writeback bid_id=%s wrote=%d errors=%d",
            draft.bid_id,
            len(receipt.files_written),
            len(receipt.errors),
        )
    except Exception as exc:  # noqa: BLE001 — vault outage must not fail the workflow
        activity.logger.warning(
            "retrospective.kb_writeback_failed bid_id=%s err=%s",
            draft.bid_id,
            exc,
        )


@activity.defn(name="retrospective_activity")
async def retrospective_activity(payload: RetrospectiveInput) -> RetrospectiveDraft:
    """Synthesise lessons + KB deltas (real LLM or stub); persist deltas to Obsidian."""
    if not is_llm_available():
        activity.logger.info("retrospective.fallback_to_stub bid_id=%s", payload.bid_id)
        return _retrospective_stub(payload)

    activity.logger.info(
        "retrospective.start bid_id=%s has_ba=%s has_wbs=%s reviews=%d",
        payload.bid_id,
        payload.ba_draft is not None,
        payload.wbs is not None,
        len(payload.reviews),
    )
    activity.heartbeat("retrospective_started")

    tracer = get_tracer()
    span = tracer.start_span(
        trace_id=str(payload.bid_id),
        name="retrospective",
        metadata={"attempt": activity.info().attempt, "tier": "flagship"},
    )
    try:
        async with langfuse_span_context(span):
            draft = await run_retrospective_agent(payload)
    except Exception as exc:  # noqa: BLE001 — any agent failure → stub fallback
        activity.logger.warning(
            "retrospective.agent_failed_using_stub bid_id=%s err=%s",
            payload.bid_id,
            exc,
        )
        draft = _retrospective_stub(payload)
    finally:
        span.end()
        await tracer.aclose()

    _persist_kb_deltas(draft)

    activity.heartbeat("retrospective_completed")
    activity.logger.info(
        "retrospective.done bid_id=%s lessons=%d kb_deltas=%d cost_usd=%.6f",
        payload.bid_id,
        len(draft.lessons),
        len(draft.kb_deltas),
        draft.llm_cost_usd or 0.0,
    )
    return draft
