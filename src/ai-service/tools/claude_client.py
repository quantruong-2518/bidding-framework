"""Thin AsyncAnthropic wrapper with ephemeral prompt caching on system prompts."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from config.claude import HAIKU, SONNET, get_claude_settings

logger = logging.getLogger(__name__)

__all__ = ["ClaudeClient", "ClaudeResponse", "HAIKU", "SONNET"]


class ClaudeResponse(BaseModel):
    """Normalized Claude completion result with token usage counters."""

    text: str
    model: str
    stop_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class ClaudeClient:
    """AsyncAnthropic wrapper enforcing the Task 1.3 caching + routing contract."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client  # lazy; injected in tests
        self._settings = get_claude_settings()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropic

        kwargs: dict[str, Any] = {
            "timeout": self._settings.timeout_seconds,
            "max_retries": self._settings.max_retries,
        }
        if self._settings.api_key:
            kwargs["api_key"] = self._settings.api_key
        if self._settings.base_url:
            kwargs["base_url"] = self._settings.base_url
        self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def generate(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        *,
        cache_system: bool = True,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> ClaudeResponse:
        """Send a Messages request; cache the system prompt via `cache_control` when enabled."""
        client = self._get_client()

        system_payload: list[dict[str, Any]] | str
        if cache_system:
            system_payload = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_payload = system

        logger.debug(
            "claude.request model=%s msgs=%d cache_system=%s",
            model,
            len(messages),
            cache_system,
        )
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_payload,
            messages=messages,
        )

        return _to_claude_response(response)


def _to_claude_response(response: Any) -> ClaudeResponse:
    """Normalize SDK response objects (and mocks) into a ClaudeResponse."""
    text_parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else ""
            )
            if text:
                text_parts.append(text)

    usage_obj = getattr(response, "usage", None)
    usage_dict: dict[str, int] = {}
    if usage_obj is not None:
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            value = getattr(usage_obj, key, None)
            if value is None and isinstance(usage_obj, dict):
                value = usage_obj.get(key)
            if value is not None:
                usage_dict[key] = int(value)

    return ClaudeResponse(
        text="".join(text_parts),
        model=getattr(response, "model", "") or "",
        stop_reason=getattr(response, "stop_reason", None),
        usage=usage_dict,
    )
