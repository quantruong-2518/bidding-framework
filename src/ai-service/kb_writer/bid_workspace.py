"""Per-bid Obsidian workspace scaffolder + snapshot writer.

Layout: **flat** — all phase files at the bid root with `NN-` prefixes for
chronological file-sort in Obsidian; reviews (which can have multiple rounds)
are the one nested folder.

```
<vault_root>/bids/<bid_id>/
  index.md
  00-bid-card.md
  01-triage.md
  02-scoping.md
  03-ba.md
  03-sa.md
  03-domain.md
  04-convergence.md
  05-hld.md
  06-wbs.md
  07-pricing.md
  08-proposal.md
  09-reviews/
    01-<reviewer>.md
    02-<reviewer>.md
  10-submission.md
  11-retrospective.md
```

Writes are atomic: content goes to a `.tmp` sibling, then `os.replace` moves
it into place. Safe under retries because the input is always the
Temporal-persisted `BidState` — overwriting yields the same bytes.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from kb_writer import templates
from kb_writer.models import WorkspaceReceipt
from workflows.models import BidState

logger = logging.getLogger(__name__)

BIDS_DIRNAME = "bids"
REVIEWS_SUBDIR = "09-reviews"


def bid_workspace_path(vault_root: str | Path, bid_id: UUID) -> Path:
    return Path(vault_root) / BIDS_DIRNAME / str(bid_id)


def ensure_workspace(vault_root: str | Path, bid_id: UUID) -> Path:
    """Idempotently create `<vault>/bids/<bid_id>/` + the reviews subfolder."""
    root = bid_workspace_path(vault_root, bid_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / REVIEWS_SUBDIR).mkdir(parents=True, exist_ok=True)
    return root


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


def _reviewer_slug(reviewer: str) -> str:
    slug = _SLUG_RE.sub("-", reviewer or "reviewer").strip("-").lower()
    return slug or "reviewer"


def write_snapshot(vault_root: str | Path, state: BidState, *, phase: str | None = None) -> WorkspaceReceipt:
    """Render every populated artifact in `state` into `<vault>/bids/<bid_id>/`.

    Best-effort: individual artifact render failures are captured in the
    receipt's `errors` list but do not raise — the workflow keeps moving.
    """
    receipt = WorkspaceReceipt(
        bid_id=str(state.bid_id),
        phase=phase or state.current_state,
        files_written=[],
        files_skipped=[],
        errors=[],
    )
    root = ensure_workspace(vault_root, state.bid_id)

    def write(filename: str, content: str) -> None:
        target = root / filename
        try:
            _write_atomic(target, content)
            receipt.files_written.append(filename)
        except Exception as exc:  # noqa: BLE001 — capture every render/write failure
            receipt.errors.append(f"{filename}: {exc}")
            logger.warning("kb_writer.write_failed path=%s err=%s", target, exc)

    # S0 bid card
    if state.bid_card is not None:
        write("00-bid-card.md", templates.render_bid_card(state.bid_card))
    else:
        receipt.files_skipped.append("00-bid-card.md")

    # S1 triage
    if state.triage is not None:
        write("01-triage.md", templates.render_triage(state.triage, bid_id=state.bid_id))
    else:
        receipt.files_skipped.append("01-triage.md")

    # S2 scoping
    if state.scoping is not None:
        write("02-scoping.md", templates.render_scoping(state.scoping, bid_id=state.bid_id))
    else:
        receipt.files_skipped.append("02-scoping.md")

    # S3a/b/c
    if state.ba_draft is not None:
        write("03-ba.md", templates.render_ba(state.ba_draft))
    else:
        receipt.files_skipped.append("03-ba.md")
    if state.sa_draft is not None:
        write("03-sa.md", templates.render_sa(state.sa_draft))
    else:
        receipt.files_skipped.append("03-sa.md")
    if state.domain_notes is not None:
        write("03-domain.md", templates.render_domain(state.domain_notes))
    else:
        receipt.files_skipped.append("03-domain.md")

    # S4 convergence
    if state.convergence is not None:
        write("04-convergence.md", templates.render_convergence(state.convergence))
    else:
        receipt.files_skipped.append("04-convergence.md")

    # S5 HLD
    if state.hld is not None:
        write("05-hld.md", templates.render_hld(state.hld))
    else:
        receipt.files_skipped.append("05-hld.md")

    # S6 WBS
    if state.wbs is not None:
        write("06-wbs.md", templates.render_wbs(state.wbs))
    else:
        receipt.files_skipped.append("06-wbs.md")

    # S7 pricing
    if state.pricing is not None:
        write("07-pricing.md", templates.render_pricing(state.pricing))
    else:
        receipt.files_skipped.append("07-pricing.md")

    # S8 proposal
    if state.proposal_package is not None:
        write("08-proposal.md", templates.render_proposal(state.proposal_package))
    else:
        receipt.files_skipped.append("08-proposal.md")

    # S9 reviews — one file per round under 09-reviews/
    for idx, record in enumerate(state.reviews, start=1):
        filename = f"{REVIEWS_SUBDIR}/{idx:02d}-{_reviewer_slug(record.reviewer)}.md"
        write(filename, templates.render_review(record, round_index=idx))

    # S10 submission
    if state.submission is not None:
        write("10-submission.md", templates.render_submission(state.submission))
    else:
        receipt.files_skipped.append("10-submission.md")

    # S11 retrospective
    if state.retrospective is not None:
        write("11-retrospective.md", templates.render_retrospective(state.retrospective))
    else:
        receipt.files_skipped.append("11-retrospective.md")

    # Index hub — always rendered; it's the user's entry point into the workspace.
    write("index.md", templates.render_index(state))

    logger.info(
        "kb_writer.snapshot_done bid=%s phase=%s written=%d skipped=%d errors=%d",
        receipt.bid_id,
        receipt.phase,
        len(receipt.files_written),
        len(receipt.files_skipped),
        len(receipt.errors),
    )
    return receipt


__all__ = ["bid_workspace_path", "ensure_workspace", "write_snapshot"]
