"""Domain LangGraph agent: retrieve -> tag -> synthesize -> critique -> (loop|END).

Haiku tags per-atom domain cues; Sonnet handles synthesis + self-critique.
Mirrors the BA / SA agent structures.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from agents.prompts.domain_agent import (
    SYSTEM_PROMPT_EXTRACT,
    SYSTEM_PROMPT_REVIEW,
    SYSTEM_PROMPT_SYNTHESIZE,
)
from tools import claude_client as claude_client_mod
from tools import kb_search as kb_search_mod
from tools.claude_client import HAIKU, SONNET
from workflows.artifacts import (
    ComplianceItem,
    DomainNotes,
    DomainPractice,
    StreamInput,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 2
CONFIDENCE_LOOP_THRESHOLD = 0.5

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class DomainState(TypedDict, total=False):
    input_req: StreamInput
    retrieved: list[dict[str, Any]]
    tags: list[dict[str, Any]]
    draft: DomainNotes | None
    critique: dict[str, Any] | None
    iteration: int
    error: str | None


def _strip_json(text: str) -> str:
    stripped = text.strip()
    stripped = _JSON_FENCE_RE.sub("", stripped)
    return stripped.strip()


def _parse_json(text: str) -> Any:
    return json.loads(_strip_json(text))


def _retrieval_query(req: StreamInput) -> str:
    head = " | ".join(atom.text[:120] for atom in req.requirements[:3])
    return f"{req.industry} {req.region} compliance best practices :: {head}".strip()


async def retrieve_similar(state: DomainState) -> DomainState:
    """Node 1 — query KB for sector-specific compliance / best-practice notes."""
    req = state["input_req"]
    query = _retrieval_query(req)
    hits = await kb_search_mod.kb_search(
        query=query,
        domain=req.industry.lower() or None,
        final_k=5,
    )
    logger.info("domain_agent.retrieve bid_id=%s hits=%d", req.bid_id, len(hits))
    return {"retrieved": hits, "iteration": 0}


async def tag_atoms(state: DomainState) -> DomainState:
    """Node 2 — Haiku applies domain tags per atom."""
    req = state["input_req"]
    if not req.requirements:
        return {"tags": []}

    user_payload = json.dumps(
        {
            "industry": req.industry,
            "region": req.region,
            "atoms": [
                {"id": atom.id, "text": atom.text, "category": atom.category}
                for atom in req.requirements
            ],
        },
        ensure_ascii=False,
    )
    client = _get_client()
    try:
        response = await client.generate(
            model=HAIKU,
            system=SYSTEM_PROMPT_EXTRACT,
            messages=[{"role": "user", "content": user_payload}],
            max_tokens=1024,
            temperature=0.0,
        )
        tags = _parse_json(response.text)
        if not isinstance(tags, list):
            raise ValueError("tagger did not return a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("domain_agent.tag_fallback err=%s", exc)
        tags = [
            {"id": atom.id, "domain_tags": ["none"], "notes": atom.text}
            for atom in req.requirements
        ]
    return {"tags": tags}


def _synthesis_user_payload(state: DomainState) -> str:
    req = state["input_req"]
    payload = {
        "bid_id": str(req.bid_id),
        "client_name": req.client_name,
        "industry": req.industry,
        "region": req.region,
        "deadline": req.deadline.isoformat(),
        "constraints": req.constraints,
        "tagged_atoms": state.get("tags", []),
        "retrieved_context": [
            {
                "source_path": hit.get("source_path"),
                "score": hit.get("score"),
                "excerpt": (hit.get("content") or "")[:800],
                "metadata": hit.get("metadata", {}),
            }
            for hit in state.get("retrieved", [])
        ],
    }
    critique = state.get("critique")
    if critique:
        payload["prior_critique"] = critique
    return json.dumps(payload, ensure_ascii=False)


def _coerce_draft(raw: dict[str, Any], req: StreamInput) -> DomainNotes:
    compliance = [ComplianceItem(**item) for item in raw.get("compliance", [])]
    best_practices = [DomainPractice(**item) for item in raw.get("best_practices", [])]

    glossary_raw = raw.get("glossary") or {}
    glossary = (
        {str(k): str(v) for k, v in glossary_raw.items()}
        if isinstance(glossary_raw, dict)
        else {}
    )

    return DomainNotes(
        bid_id=req.bid_id,
        industry=req.industry,
        compliance=compliance,
        best_practices=best_practices,
        industry_constraints=list(raw.get("industry_constraints", [])),
        glossary=glossary,
        confidence=float(raw.get("confidence", 0.4)),
        sources=list(raw.get("sources", [])),
    )


async def synthesize_draft(state: DomainState) -> DomainState:
    req = state["input_req"]
    client = _get_client()
    user_payload = _synthesis_user_payload(state)

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_payload}]
    last_error: str | None = None
    for attempt in range(2):
        try:
            response = await client.generate(
                model=SONNET,
                system=SYSTEM_PROMPT_SYNTHESIZE,
                messages=messages,
                max_tokens=4096,
                temperature=0.2,
            )
            raw = _parse_json(response.text)
            if not isinstance(raw, dict):
                raise ValueError("synthesizer did not return a JSON object")
            draft = _coerce_draft(raw, req)
            iteration = int(state.get("iteration", 0)) + 1
            return {"draft": draft, "iteration": iteration, "error": None}
        except (json.JSONDecodeError, ValueError, ValidationError) as exc:
            last_error = str(exc)
            logger.warning(
                "domain_agent.synth_parse_err attempt=%d err=%s",
                attempt + 1,
                last_error,
            )
            messages = [
                {"role": "user", "content": user_payload},
                {
                    "role": "user",
                    "content": (
                        "Your previous response could not be parsed as JSON matching the schema. "
                        f"Error: {last_error}. Return ONLY valid JSON per the system schema."
                    ),
                },
            ]

    iteration = int(state.get("iteration", 0)) + 1
    return {"draft": None, "iteration": iteration, "error": last_error}


async def self_critique(state: DomainState) -> DomainState:
    draft = state.get("draft")
    if draft is None:
        return {
            "critique": {
                "coverage_gaps": ["draft missing"],
                "quality_issues": ["draft synthesis failed"],
                "confidence": 0.0,
            }
        }

    client = _get_client()
    user_payload = json.dumps(
        {
            "tags": state.get("tags", []),
            "draft": draft.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    try:
        response = await client.generate(
            model=SONNET,
            system=SYSTEM_PROMPT_REVIEW,
            messages=[{"role": "user", "content": user_payload}],
            max_tokens=1024,
            temperature=0.0,
        )
        critique = _parse_json(response.text)
        if not isinstance(critique, dict):
            raise ValueError("critique did not return a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("domain_agent.critique_fallback err=%s", exc)
        critique = {
            "coverage_gaps": [],
            "quality_issues": [f"critique parse failure: {exc}"],
            "confidence": float(draft.confidence),
        }
    else:
        critique.setdefault("coverage_gaps", [])
        critique.setdefault("quality_issues", [])
        critique.setdefault("confidence", float(draft.confidence))

    return {"critique": critique}


def _route_after_critique(state: DomainState) -> str:
    draft = state.get("draft")
    critique = state.get("critique") or {}
    iteration = int(state.get("iteration", 0))
    confidence = float(critique.get("confidence", 0.0))
    retrieved = state.get("retrieved") or []

    if draft is None:
        return END
    if not retrieved:
        draft.confidence = max(float(draft.confidence), confidence)
        return END
    if confidence < CONFIDENCE_LOOP_THRESHOLD and iteration < MAX_ITERATIONS:
        logger.info(
            "domain_agent.loop iteration=%d confidence=%.2f -> re-synthesize",
            iteration,
            confidence,
        )
        return "synthesize_draft"
    draft.confidence = max(float(draft.confidence), confidence)
    return END


@lru_cache(maxsize=1)
def _build_graph() -> Any:
    graph = StateGraph(DomainState)
    graph.add_node("retrieve_similar", retrieve_similar)
    graph.add_node("tag_atoms", tag_atoms)
    graph.add_node("synthesize_draft", synthesize_draft)
    graph.add_node("self_critique", self_critique)

    graph.add_edge(START, "retrieve_similar")
    graph.add_edge("retrieve_similar", "tag_atoms")
    graph.add_edge("tag_atoms", "synthesize_draft")
    graph.add_edge("synthesize_draft", "self_critique")
    graph.add_conditional_edges(
        "self_critique",
        _route_after_critique,
        {"synthesize_draft": "synthesize_draft", END: END},
    )
    return graph.compile()


def _get_client() -> claude_client_mod.ClaudeClient:
    return claude_client_mod.ClaudeClient()


async def run_domain_agent(input_req: StreamInput) -> DomainNotes:
    """Entrypoint — run the Domain graph and return notes (empty if LLM failed)."""
    compiled = _build_graph()
    initial: DomainState = {"input_req": input_req, "iteration": 0}
    final_state: DomainState = await compiled.ainvoke(initial)  # type: ignore[assignment]

    draft = final_state.get("draft")
    if draft is not None:
        return draft

    logger.error(
        "domain_agent.no_draft bid_id=%s err=%s",
        input_req.bid_id,
        final_state.get("error"),
    )
    return DomainNotes(
        bid_id=input_req.bid_id,
        industry=input_req.industry,
        compliance=[],
        best_practices=[],
        industry_constraints=[],
        glossary={},
        confidence=0.0,
        sources=[],
    )
