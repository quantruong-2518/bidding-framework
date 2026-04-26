"""S0.5 file role classifier.

Picks one of ``rfp / appendix / qa / reference / previous_engagement`` per
:class:`ParsedFile`. LLM-driven (nano tier, ~$0.0002/file) when the active
provider has a key; falls back to a filename-keyword heuristic otherwise.

Contract (Rule B): the wrapper NEVER raises. On any LLM failure it logs a
warning and returns the heuristic result so the upstream parse pipeline
keeps progressing.
"""

from __future__ import annotations

import logging
from typing import Literal, get_args

from agents.prompts.file_classifier import (
    SYSTEM_PROMPT_FILE_CLASSIFIER_EN,
    SYSTEM_PROMPT_FILE_CLASSIFIER_VI,
)
from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.base import FileRole, ParsedFile

logger = logging.getLogger(__name__)

_TIER = "nano"
_VALID_ROLES = set(get_args(FileRole))

# Filename keyword → role. Order matters — first hit wins.
_FILENAME_RULES: tuple[tuple[tuple[str, ...], FileRole], ...] = (
    (("q&a", "qa", "question", "addendum", "clarification"), "qa"),
    (("appendix", "annex", "schedule"), "appendix"),
    (("rfp", "rfq", "tender", "ito", "itb"), "rfp"),
    (("previous", "prior", "past", "old-bid", "engagement"), "previous_engagement"),
)


def _heuristic_role(filename: str) -> FileRole:
    """Rule-based classifier — used when the LLM is unavailable or fails."""
    name = (filename or "").lower()
    for keywords, role in _FILENAME_RULES:
        if any(kw in name for kw in keywords):
            return role
    return "reference"


def _content_sample(file: ParsedFile, *, limit: int = 500) -> str:
    """Trim the body to ~500 chars for the LLM classifier."""
    text = file.raw_text or ""
    return text[:limit].strip()


def _normalise_role(raw: str) -> FileRole | None:
    """Map a raw LLM response to a valid :data:`FileRole` token."""
    if not raw:
        return None
    token = raw.strip().lower().strip("\"'")
    # The model sometimes returns the role wrapped in JSON or extra prose;
    # we accept any token that contains the role keyword.
    for role in _VALID_ROLES:
        if role in token:
            return role  # type: ignore[return-value]
    return None


async def classify_file_role(
    file: ParsedFile,
    *,
    client: LLMClient | None = None,
    bid_id_for_trace: str | None = None,
) -> FileRole:
    """Return the :data:`FileRole` for ``file``.

    LLM path opens a single :class:`LLMConversation` turn at the nano tier;
    on any failure (no key, parse error, network) we degrade to the heuristic.
    The deterministic-test seam works because conftest's autouse fixture
    scrubs the provider keys; the call lands in the FakeLLMClient — which
    returns empty text by default, triggering the post-LLM heuristic
    fallback path naturally.
    """
    from config.llm import is_llm_available

    heuristic = _heuristic_role(file.name)

    if not is_llm_available():
        logger.debug("file_classifier.stub_path file=%s role=%s", file.name, heuristic)
        return heuristic

    prompt = (
        SYSTEM_PROMPT_FILE_CLASSIFIER_VI
        if file.language == "vi"
        else SYSTEM_PROMPT_FILE_CLASSIFIER_EN
    )
    conv = LLMConversation(
        system=prompt,
        client=client,
        default_tier=_TIER,
        default_max_tokens=16,
        default_temperature=0.0,
        trace_id=bid_id_for_trace,
    )
    user_payload = (
        f"Filename: {file.name}\n"
        f"MIME: {file.mime}\n"
        f"PageCount: {file.page_count}\n"
        f"Sample: {_content_sample(file)}"
    )
    try:
        response = await conv.send(
            user_payload, tier=_TIER, node_name="file_classifier.classify"
        )
    except Exception as exc:  # noqa: BLE001 — never break parse on LLM glitch
        logger.warning("file_classifier.send_failed file=%s err=%s", file.name, exc)
        return heuristic

    role = _normalise_role(response.text)
    if role is None:
        logger.warning(
            "file_classifier.unparseable file=%s raw=%r", file.name, response.text[:60]
        )
        return heuristic
    return role


__all__ = ["classify_file_role"]
