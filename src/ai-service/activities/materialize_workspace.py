"""Wave 2A — vault-only materialization activity.

This is the post-confirm path: api-gateway has already pinned the parse-session
payload (atoms / anchor / summary / manifest / conflicts) and now hands it to
us so we can write the vault tree atomically. NO LLM calls, NO Postgres reads
— pure vault writer.

It's effectively a thin wrapper around
:func:`activities.context_synthesis._run_materialize`, exposed as its own
activity so callers can dispatch the materialize step independently of the
preview pipeline (e.g. when api-gateway already has a parse_session row and
wants to retry the vault write without re-parsing).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from temporalio import activity

logger = logging.getLogger(__name__)


class MaterializeWorkspaceInput(BaseModel):
    """Input — same fields as the materialize branch of ContextSynthesisInput."""

    parse_session_id: str
    bid_id: str
    tenant_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    vault_root: str = ""


class MaterializeWorkspaceOutput(BaseModel):
    """Result — list of files written + atom count for the audit log."""

    bid_id: str
    files_written: list[str] = Field(default_factory=list)
    atoms_written: int = 0
    conflicts_written: int = 0


@activity.defn(name="materialize_workspace_activity")
async def materialize_workspace_activity(
    payload: MaterializeWorkspaceInput,
) -> MaterializeWorkspaceOutput:
    """Write the bid vault tree from a confirmed parse_session payload."""
    from activities.context_synthesis import (
        ContextSynthesisInput,
        _run_materialize,
    )

    activity.logger.info(
        "materialize_workspace.start bid_id=%s session=%s",
        payload.bid_id,
        payload.parse_session_id,
    )
    inner_input = ContextSynthesisInput(
        mode="materialize",
        parse_session_id=payload.parse_session_id,
        tenant_id=payload.tenant_id,
        bid_id=payload.bid_id,
        payload=payload.payload,
        vault_root=payload.vault_root,
        files=[],
    )
    result = await _run_materialize(inner_input)
    return MaterializeWorkspaceOutput(
        bid_id=payload.bid_id,
        files_written=result.files_written,
        atoms_written=len(result.atoms),
        conflicts_written=len(result.conflicts),
    )


__all__ = [
    "MaterializeWorkspaceInput",
    "MaterializeWorkspaceOutput",
    "materialize_workspace_activity",
]
