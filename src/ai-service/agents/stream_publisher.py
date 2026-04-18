"""Phase 2.5 agent token publisher — throttled Redis PUBLISH for streaming LLM output.

Used by BA/SA/Domain LangGraph activities when ``ANTHROPIC_API_KEY`` is set
(streaming path). Buffers ``text_delta`` chunks + flushes on whichever comes
first: 150 ms window or 200 accumulated chars. Best-effort — Redis outages log
and are swallowed so the workflow never fails on a streaming hiccup.

Activity wrappers bind a :class:`TokenPublisher` into the current async context
via :func:`stream_context`. The node-level ``_call_llm`` helper in each agent
reads :func:`get_current_publisher` to decide whether to use
``ClaudeClient.generate_stream`` (streaming path) or fall back to the legacy
``generate`` (unit-test / no-key path).

Payload shape published to ``bid.events.channel.{bid_id}``::

    {
        "type": "agent_token",
        "agent": "ba" | "sa" | "domain",
        "node": "<graph-node-name>",
        "attempt": int,       # activity.info().attempt — frontend de-dupes by this
        "seq": int,           # monotonic per (agent, node, attempt), starts at 1
        "text_delta": str,    # accumulated chunk (may contain multiple deltas)
        "done": bool,         # true on message_stop for the node
    }
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Literal

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

BID_EVENTS_CHANNEL_PREFIX = "bid.events.channel"

AgentName = Literal["ba", "sa", "domain"]

_CURRENT_PUBLISHER: contextvars.ContextVar["TokenPublisher | None"] = (
    contextvars.ContextVar("agent_stream_publisher", default=None)
)


def get_current_publisher() -> "TokenPublisher | None":
    """Return the publisher bound to the current async context, or ``None``."""
    return _CURRENT_PUBLISHER.get()


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


class TokenPublisher:
    """Throttled Redis publisher for agent token streams (best-effort)."""

    def __init__(
        self,
        *,
        bid_id: str,
        agent: AgentName,
        attempt: int,
        redis_url: str | None = None,
        client: Any | None = None,
        interval_seconds: float = 0.150,
        threshold_chars: int = 200,
    ) -> None:
        self._bid_id = bid_id
        self._agent = agent
        self._attempt = attempt
        self._channel = f"{BID_EVENTS_CHANNEL_PREFIX}.{bid_id}"
        self._redis_url = redis_url or _redis_url()
        self._client = client  # injected in tests
        self._interval = interval_seconds
        self._threshold = threshold_chars
        self._node: str | None = None
        self._seq = 0
        self._buffer: list[str] = []
        self._buffered_chars = 0
        self._flush_handle: asyncio.TimerHandle | None = None
        self._closed = False

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def set_node(self, node: str) -> None:
        """Switch the active LLM node; flushes prior node's pending buffer."""
        if self._node is not None and self._buffer:
            await self._flush_now()
        self._node = node
        self._seq = 0

    async def push(self, text_delta: str) -> None:
        """Append a text delta. Immediate publish on threshold hit; else 150 ms timer."""
        if self._closed or not text_delta or self._node is None:
            return
        self._buffer.append(text_delta)
        self._buffered_chars += len(text_delta)
        if self._buffered_chars >= self._threshold:
            await self._flush_now()
            return
        if self._flush_handle is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self._flush_handle = loop.call_later(
                self._interval,
                lambda: asyncio.create_task(self._flush_now()),
            )

    async def mark_done(self) -> None:
        """Flush pending buffer + emit a ``done=true`` event for the current node."""
        if self._closed or self._node is None:
            return
        await self._flush_now()
        self._seq += 1
        await self._publish(
            {
                "type": "agent_token",
                "agent": self._agent,
                "node": self._node,
                "attempt": self._attempt,
                "seq": self._seq,
                "text_delta": "",
                "done": True,
            }
        )

    async def _flush_now(self) -> None:
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        if not self._buffer or self._node is None:
            return
        text = "".join(self._buffer)
        self._buffer.clear()
        self._buffered_chars = 0
        self._seq += 1
        await self._publish(
            {
                "type": "agent_token",
                "agent": self._agent,
                "node": self._node,
                "attempt": self._attempt,
                "seq": self._seq,
                "text_delta": text,
                "done": False,
            }
        )

    async def _publish(self, payload: dict[str, Any]) -> None:
        try:
            client = self._get_client()
            await client.publish(self._channel, json.dumps(payload))
        except Exception as exc:  # noqa: BLE001 — streaming must not block workflow
            logger.warning(
                "agent_stream.publish.failed bid=%s agent=%s node=%s err=%s",
                self._bid_id,
                self._agent,
                self._node,
                exc,
            )

    async def aclose(self) -> None:
        """Cancel any pending flush + close the Redis client. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass


@asynccontextmanager
async def stream_context(publisher: TokenPublisher) -> AsyncIterator[TokenPublisher]:
    """Bind ``publisher`` to the current async context for agent node access."""
    token = _CURRENT_PUBLISHER.set(publisher)
    try:
        yield publisher
    finally:
        _CURRENT_PUBLISHER.reset(token)


__all__ = [
    "AgentName",
    "BID_EVENTS_CHANNEL_PREFIX",
    "TokenPublisher",
    "get_current_publisher",
    "stream_context",
]
