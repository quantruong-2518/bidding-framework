"""CLI: seed sample markdown documents into Qdrant."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from config.qdrant import ensure_collection, get_qdrant_client
from rag.indexer import index_markdown_file

logger = logging.getLogger(__name__)

SAMPLE_DIR = Path(__file__).parent / "sample_docs"


async def run() -> int:
    """Index every .md file under sample_docs/. Returns chunks indexed."""
    client = await get_qdrant_client()
    await ensure_collection(client)

    files = sorted(SAMPLE_DIR.glob("*.md"))
    if not files:
        logger.warning("rag.seed no_files dir=%s", SAMPLE_DIR)
        return 0

    total = 0
    for path in files:
        chunks = await index_markdown_file(client, str(path))
        logger.info("rag.seed indexed file=%s chunks=%d", path.name, chunks)
        total += chunks
    logger.info("rag.seed done total_chunks=%d files=%d", total, len(files))
    return total


def main() -> None:
    """Sync entrypoint for `python -m rag.seed`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
