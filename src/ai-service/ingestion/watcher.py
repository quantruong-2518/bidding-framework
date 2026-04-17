"""Filesystem watcher for the Obsidian vault — watchdog with polling fallback."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OnChange = Callable[[Path], Awaitable[None]]

_SKIP_DIR_NAMES = {".obsidian", ".git", ".trash", "node_modules"}


def _should_watch(path: Path) -> bool:
    """Return True if path is a markdown file outside Obsidian internals."""
    if path.suffix.lower() != ".md":
        return False
    return not any(part in _SKIP_DIR_NAMES for part in path.parts)


class VaultWatcher:
    """Watch a vault and invoke on_change for .md files; debounces bursty events."""

    def __init__(
        self,
        root: Path,
        on_change: OnChange,
        *,
        debounce_ms: int = 500,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._root = root.resolve()
        self._on_change = on_change
        self._debounce = debounce_ms / 1000.0
        self._poll_interval = poll_interval_seconds
        self._pending: dict[Path, asyncio.TimerHandle] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = asyncio.Event()
        self._backend: str = "unknown"

    @property
    def backend(self) -> str:
        """Return 'watchdog' or 'polling', whichever the watcher is using."""
        return self._backend

    def enqueue(self, path: Path) -> None:
        """Public hook for tests: schedule a debounced dispatch for path."""
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        self._schedule(path)

    def _schedule(self, path: Path) -> None:
        """Schedule a debounced fire for path, cancelling any pending fire."""
        existing = self._pending.pop(path, None)
        if existing is not None:
            existing.cancel()
        assert self._loop is not None
        handle = self._loop.call_later(self._debounce, self._fire, path)
        self._pending[path] = handle

    def _fire(self, path: Path) -> None:
        """Invoke the async callback as a task; swallow/surface errors via log."""
        self._pending.pop(path, None)

        async def _run() -> None:
            try:
                await self._on_change(path)
            except Exception:  # noqa: BLE001
                logger.exception("ingestion.watcher callback_failed path=%s", path)

        assert self._loop is not None
        self._loop.create_task(_run())

    async def _watchdog_backend(self) -> None:
        """Run watchdog-based filesystem events on a thread pool."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            raise

        class _Handler(FileSystemEventHandler):  # type: ignore[misc]
            def __init__(self, outer: VaultWatcher) -> None:
                self._outer = outer

            def _maybe_schedule(self, raw_path: str) -> None:
                p = Path(raw_path)
                if not _should_watch(p):
                    return
                loop = self._outer._loop
                if loop is None:
                    return
                loop.call_soon_threadsafe(self._outer._schedule, p)

            def on_modified(self, event: Any) -> None:  # type: ignore[override]
                if not event.is_directory:
                    self._maybe_schedule(event.src_path)

            def on_created(self, event: Any) -> None:  # type: ignore[override]
                if not event.is_directory:
                    self._maybe_schedule(event.src_path)

            def on_moved(self, event: Any) -> None:  # type: ignore[override]
                if not event.is_directory:
                    self._maybe_schedule(event.dest_path)

        observer = Observer()
        observer.schedule(_Handler(self), str(self._root), recursive=True)
        observer.start()
        logger.info("ingestion.watcher backend=watchdog root=%s", self._root)
        try:
            await self._stop.wait()
        finally:
            observer.stop()
            observer.join(timeout=2)

    async def _polling_backend(self) -> None:
        """Stat-based polling fallback that scans mtime diffs."""
        logger.info(
            "ingestion.watcher backend=polling root=%s interval=%.1fs",
            self._root,
            self._poll_interval,
        )
        known: dict[Path, float] = {}
        # Prime the mtime table so the first tick doesn't flood.
        for path in self._root.rglob("*.md"):
            if _should_watch(path):
                known[path] = path.stat().st_mtime
        while not self._stop.is_set():
            for path in self._root.rglob("*.md"):
                if not _should_watch(path):
                    continue
                try:
                    mtime = path.stat().st_mtime
                except FileNotFoundError:
                    continue
                prev = known.get(path)
                if prev is None or mtime > prev:
                    known[path] = mtime
                    self._schedule(path)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                continue

    async def watch(self) -> None:
        """Run the configured backend until stop() is called."""
        self._loop = asyncio.get_event_loop()
        self._stop.clear()
        try:
            import watchdog  # noqa: F401
        except ImportError:
            self._backend = "polling"
            await self._polling_backend()
            return
        self._backend = "watchdog"
        try:
            await self._watchdog_backend()
        except ImportError:
            self._backend = "polling"
            await self._polling_backend()

    def stop(self) -> None:
        """Signal the watcher to unwind on the next loop tick."""
        self._stop.set()
        for handle in self._pending.values():
            handle.cancel()
        self._pending.clear()
