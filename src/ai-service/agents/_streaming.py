"""Phase 2.5 streaming dispatch helper — shared by BA / SA / Domain agents.

Each LLM node (Haiku extract / Sonnet synth / Sonnet critique) in the three
agents calls :func:`call_llm` instead of :meth:`ClaudeClient.generate`
directly. When a :class:`TokenPublisher` is bound to the current async context
(via :func:`stream_context` in the activity wrapper), this helper routes the
call through :meth:`ClaudeClient.generate_stream` + forwards each text delta
to the publisher. Without a bound publisher it falls through to the legacy
one-shot path so unit tests + the stub-fallback branch keep working.
"""

from __future__ import annotations

from typing import Any

from agents.stream_publisher import get_current_publisher
from tools.claude_client import ClaudeClient, ClaudeResponse


async def call_llm(
    client: ClaudeClient,
    *,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    node_name: str,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> ClaudeResponse:
    """Dispatch to :meth:`generate_stream` when a publisher is bound, else :meth:`generate`.

    ``node_name`` identifies the LangGraph node (``extract_requirements``,
    ``synthesize_draft``, etc.) so downstream subscribers can segment the UX
    per-node.
    """
    pub = get_current_publisher()
    if pub is None:
        return await client.generate(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            node_name=node_name,
        )
    await pub.set_node(node_name)
    try:
        return await client.generate_stream(
            model=model,
            system=system,
            messages=messages,
            on_token=pub.push,
            max_tokens=max_tokens,
            temperature=temperature,
            node_name=node_name,
        )
    finally:
        await pub.mark_done()


__all__ = ["call_llm"]
