"""CLI entry point for the ingestion service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from config.ingestion import get_ingestion_settings
from ingestion.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the ingestion CLI."""
    parser = argparse.ArgumentParser(prog="ingestion", description="Obsidian vault ingestion.")
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Vault root (defaults to KB_VAULT_PATH env or ingestion settings).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and watch for file changes after the initial index.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser.parse_args()


def _resolve_vault(args: argparse.Namespace) -> Path:
    """Return the vault path from --vault, KB_VAULT_PATH env, or settings."""
    if args.vault is not None:
        return args.vault.resolve()
    env = os.environ.get("KB_VAULT_PATH")
    if env:
        return Path(env).resolve()
    return get_ingestion_settings().vault_path.resolve()


async def _build_qdrant_client() -> Any:
    """Lazily build a Qdrant client; None at runtime surfaces a clearer error."""
    from config.qdrant import ensure_collection, get_qdrant_client

    client = await get_qdrant_client()
    await ensure_collection(client)
    return client


async def _amain(args: argparse.Namespace) -> int:
    """Async CLI body — initial index, plus optional watch."""
    root = _resolve_vault(args)
    logger.info("ingestion.cli vault=%s watch=%s", root, args.watch)
    client = await _build_qdrant_client()
    service = IngestionService(client)
    if args.watch:
        await service.run(root)
    else:
        await service.initial_index(root)
    return 0


def main() -> int:
    """Synchronous entry point for python -m ingestion."""
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        logger.info("ingestion.cli_interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
