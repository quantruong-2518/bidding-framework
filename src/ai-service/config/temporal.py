"""Temporal client configuration + factory."""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

TASK_QUEUE_DEFAULT = "bid-workflow-queue"


class TemporalSettings(BaseSettings):
    """Environment-driven Temporal connection + worker settings."""

    model_config = SettingsConfigDict(env_prefix="TEMPORAL_", case_sensitive=False)

    host: str = "temporal:7233"
    namespace: str = "default"
    task_queue: str = TASK_QUEUE_DEFAULT
    tls: bool = False


@lru_cache(maxsize=1)
def get_settings() -> TemporalSettings:
    """Process-wide settings singleton."""
    return TemporalSettings()


async def get_temporal_client():  # type: ignore[no-untyped-def]
    """Return a connected Temporal client; imported lazily to keep cold starts light."""
    from temporalio.client import Client  # local import: optional at module load
    from temporalio.contrib.pydantic import pydantic_data_converter

    settings = get_settings()
    logger.info("temporal.connect host=%s namespace=%s", settings.host, settings.namespace)
    return await Client.connect(
        settings.host,
        namespace=settings.namespace,
        data_converter=pydantic_data_converter,
    )
