"""Temporal activity wrapper around `kb_writer.bid_workspace.write_snapshot`.

The activity is **best-effort**: it catches every exception + turns it into a
logged warning. The workflow should set a short `start_to_close_timeout` (≤30s)
and a lenient retry policy — a full vault that declines writes must not block
bid completion.
"""

from __future__ import annotations

import logging

from temporalio import activity

from config.ingestion import get_ingestion_settings
from kb_writer.bid_workspace import write_snapshot
from kb_writer.models import WorkspaceInput, WorkspaceReceipt

logger = logging.getLogger(__name__)


def _default_vault_root() -> str:
    return str(get_ingestion_settings().vault_path)


@activity.defn(name="workspace_snapshot_activity")
async def workspace_snapshot_activity(payload: WorkspaceInput) -> WorkspaceReceipt:
    """Render the current BidState into `<vault>/bids/<bid_id>/*.md`."""
    vault_root = payload.vault_root or _default_vault_root()
    activity.logger.info(
        "workspace_snapshot.start bid=%s phase=%s vault=%s",
        payload.bid_state.bid_id,
        payload.phase,
        vault_root,
    )
    try:
        receipt = write_snapshot(vault_root, payload.bid_state, phase=payload.phase)
    except Exception as exc:  # noqa: BLE001 — never fail the workflow on vault issues
        activity.logger.warning(
            "workspace_snapshot.failed bid=%s phase=%s err=%s",
            payload.bid_state.bid_id,
            payload.phase,
            exc,
        )
        return WorkspaceReceipt(
            bid_id=str(payload.bid_state.bid_id),
            phase=payload.phase,
            files_written=[],
            files_skipped=[],
            errors=[f"snapshot failed: {exc}"],
        )

    activity.logger.info(
        "workspace_snapshot.done bid=%s phase=%s written=%d errors=%d",
        receipt.bid_id,
        receipt.phase,
        len(receipt.files_written),
        len(receipt.errors),
    )
    return receipt
