"""I/O DTOs for the per-bid workspace writer."""

from __future__ import annotations

from pydantic import BaseModel, Field

from workflows.models import BidState


class WorkspaceInput(BaseModel):
    """Sent to `workspace_snapshot_activity` after each phase completes."""

    vault_root: str = Field(description="Absolute path to the Obsidian vault root (KB_VAULT_PATH).")
    phase: str = Field(description="Current workflow state literal (S0_DONE, S2_DONE, …). Used in frontmatter only.")
    bid_state: BidState


class WorkspaceReceipt(BaseModel):
    """Returned by `workspace_snapshot_activity` — useful for logging + debugging."""

    bid_id: str
    phase: str
    files_written: list[str] = Field(default_factory=list)
    files_skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


__all__ = ["WorkspaceInput", "WorkspaceReceipt"]
