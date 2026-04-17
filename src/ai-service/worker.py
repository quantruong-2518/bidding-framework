"""Temporal worker entry point — registers the bid workflow + activities."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from activities.assembly import assembly_activity
from activities.ba_analysis import ba_analysis_activity
from activities.bid_workspace import workspace_snapshot_activity
from activities.commercial import commercial_activity
from activities.convergence import convergence_activity
from activities.domain_mining import domain_mining_activity
from activities.intake import intake_activity
from activities.notify import notify_approval_needed_activity
from activities.retrospective import retrospective_activity
from activities.review import review_activity
from activities.sa_analysis import sa_analysis_activity
from activities.scoping import scoping_activity
from activities.solution_design import solution_design_activity
from activities.submission import submission_activity
from activities.triage import triage_activity
from activities.wbs import wbs_activity
from config.temporal import get_settings
from workflows.bid_workflow import BidWorkflow

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _run() -> None:
    settings = get_settings()
    logger.info(
        "worker.connect host=%s namespace=%s queue=%s",
        settings.host,
        settings.namespace,
        settings.task_queue,
    )
    client = await Client.connect(
        settings.host,
        namespace=settings.namespace,
        data_converter=pydantic_data_converter,
    )

    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[BidWorkflow],
        activities=[
            # S0..S2 (Phase 1)
            intake_activity,
            triage_activity,
            scoping_activity,
            # S3a/b/c real LangGraph-backed agents (Phase 2.2 — fall back to
            # deterministic stubs when ANTHROPIC_API_KEY is unset).
            ba_analysis_activity,
            sa_analysis_activity,
            domain_mining_activity,
            # S4 heuristic convergence + S5..S11 stubs (Phase 2.1)
            convergence_activity,
            solution_design_activity,
            wbs_activity,
            commercial_activity,
            assembly_activity,
            review_activity,
            submission_activity,
            retrospective_activity,
            # Per-bid vault writer — called after every phase completes.
            workspace_snapshot_activity,
            # Phase 2.4 — approval_needed notification for the S9 gate.
            notify_approval_needed_activity,
        ],
    )

    stop_event = asyncio.Event()

    def _stop(*_args: Any) -> None:
        logger.info("worker.shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:  # Windows / restricted envs
            signal.signal(sig, _stop)

    async with worker:
        logger.info("worker.ready queue=%s", settings.task_queue)
        await stop_event.wait()
    logger.info("worker.stopped")


def main() -> None:
    """Module entry point — `python worker.py` inside the ai-service container."""
    _configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
