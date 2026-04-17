"""Temporal worker entry point — registers the bid workflow + activities."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from activities.intake import intake_activity
from activities.scoping import scoping_activity
from activities.triage import triage_activity
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
        activities=[intake_activity, triage_activity, scoping_activity],
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
