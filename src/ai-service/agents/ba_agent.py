"""BA LangGraph agent: retrieve -> extract -> synthesize -> critique -> (loop|END).

Haiku handles extraction; Sonnet handles synthesis + self-critique.
All Claude calls enable ephemeral prompt caching on the system prompt.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from agents.models import (
    BARequirements,
    BusinessRequirementsDraft,
    FunctionalRequirement,
    RiskItem,
    SimilarProject,
)
from agents.prompts.ba_agent import (
    SYSTEM_PROMPT_EXTRACT,
    SYSTEM_PROMPT_REVIEW,
    SYSTEM_PROMPT_SYNTHESIZE,
)
from tools import claude_client as claude_client_mod
from tools import kb_search as kb_search_mod
from tools.claude_client import HAIKU, SONNET

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 2  # initial synthesize + at most one retry after critique
CONFIDENCE_LOOP_THRESHOLD = 0.5

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class BAState(TypedDict, total=False):
    """LangGraph working state for the BA agent."""

    input_req: BARequirements
    retrieved: list[dict[str, Any]]
    extracted_atoms: list[dict[str, Any]]
    draft: BusinessRequirementsDraft | None
    critique: dict[str, Any] | None
    iteration: int
    error: str | None


def _strip_json(text: str) -> str:
    """Remove optional ```json fences an LLM may emit despite instructions."""
    stripped = text.strip()
    stripped = _JSON_FENCE_RE.sub("", stripped)
    return stripped.strip()


def _parse_json(text: str) -> Any:
    return json.loads(_strip_json(text))


def _retrieval_query(req: BARequirements) -> str:
    head_titles = " | ".join(atom.text[:120] for atom in req.requirements[:3])
    return f"{req.client_name} {req.industry} {req.region} :: {head_titles}".strip()


async def retrieve_similar(state: BAState) -> BAState:
    """Node 1 — query KB for similar projects/domain context."""
    req = state["input_req"]
    query = _retrieval_query(req)
    hits = await kb_search_mod.kb_search(
        query=query,
        domain=req.industry.lower() or None,
        client=req.client_name or None,
        final_k=5,
    )
    logger.info("ba_agent.retrieve bid_id=%s hits=%d", req.bid_id, len(hits))
    return {"retrieved": hits, "iteration": 0}


async def extract_requirements(state: BAState) -> BAState:
    """Node 2 — Haiku normalises raw atoms into structured extraction output."""
    req = state["input_req"]
    if not req.requirements:
        return {"extracted_atoms": []}

    user_payload = json.dumps(
        [
            {"id": atom.id, "text": atom.text, "category": atom.category}
            for atom in req.requirements
        ],
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
        atoms = _parse_json(response.text)
        if not isinstance(atoms, list):
            raise ValueError("extractor did not return a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("ba_agent.extract_fallback err=%s", exc)
        atoms = [
            {
                "id": atom.id,
                "title": atom.text[:80],
                "category": atom.category,
                "priority": "SHOULD",
                "summary": atom.text,
            }
            for atom in req.requirements
        ]
    return {"extracted_atoms": atoms}


def _synthesis_user_payload(state: BAState) -> str:
    req = state["input_req"]
    payload = {
        "bid_id": str(req.bid_id),
        "client_name": req.client_name,
        "industry": req.industry,
        "region": req.region,
        "deadline": req.deadline.isoformat(),
        "constraints": req.constraints,
        "extracted_atoms": state.get("extracted_atoms", []),
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


def _coerce_draft(raw: dict[str, Any], req: BARequirements) -> BusinessRequirementsDraft:
    """Convert a JSON blob from Sonnet into a validated BusinessRequirementsDraft."""
    scope = raw.get("scope") or {}
    if not isinstance(scope, dict):
        scope = {"in_scope": [], "out_of_scope": []}
    scope.setdefault("in_scope", [])
    scope.setdefault("out_of_scope", [])

    functional = [
        FunctionalRequirement(**item) for item in raw.get("functional_requirements", [])
    ]
    risks = [RiskItem(**item) for item in raw.get("risks", [])]
    similar = [SimilarProject(**item) for item in raw.get("similar_projects", [])]

    return BusinessRequirementsDraft(
        bid_id=req.bid_id,
        executive_summary=raw.get("executive_summary", ""),
        business_objectives=list(raw.get("business_objectives", [])),
        scope={
            "in_scope": list(scope.get("in_scope", [])),
            "out_of_scope": list(scope.get("out_of_scope", [])),
        },
        functional_requirements=functional,
        assumptions=list(raw.get("assumptions", [])),
        constraints=list(raw.get("constraints", req.constraints)),
        success_criteria=list(raw.get("success_criteria", [])),
        risks=risks,
        similar_projects=similar,
        confidence=float(raw.get("confidence", 0.4)),
        sources=list(raw.get("sources", [])),
    )


async def synthesize_draft(state: BAState) -> BAState:
    """Node 3 — Sonnet drafts the BusinessRequirementsDraft; retry once on parse failure."""
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
                "ba_agent.synth_parse_err attempt=%d err=%s", attempt + 1, last_error
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


async def self_critique(state: BAState) -> BAState:
    """Node 4 — Sonnet critiques the draft and emits confidence + gap list."""
    draft = state.get("draft")
    req = state["input_req"]
    if draft is None:
        return {
            "critique": {
                "coverage_gaps": [atom.id for atom in req.requirements],
                "quality_issues": ["draft synthesis failed"],
                "confidence": 0.0,
            }
        }

    client = _get_client()
    user_payload = json.dumps(
        {
            "atoms": state.get("extracted_atoms", []),
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
        logger.warning("ba_agent.critique_fallback err=%s", exc)
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


def _route_after_critique(state: BAState) -> str:
    draft = state.get("draft")
    critique = state.get("critique") or {}
    iteration = int(state.get("iteration", 0))
    confidence = float(critique.get("confidence", 0.0))

    if draft is None:
        return END
    if confidence < CONFIDENCE_LOOP_THRESHOLD and iteration < MAX_ITERATIONS:
        logger.info(
            "ba_agent.loop iteration=%d confidence=%.2f -> re-synthesize",
            iteration,
            confidence,
        )
        return "synthesize_draft"
    # Persist critique confidence onto the draft for downstream consumers.
    draft.confidence = max(float(draft.confidence), confidence)
    return END


@lru_cache(maxsize=1)
def _build_graph() -> Any:
    """Compile the BA LangGraph graph once at module load."""
    graph = StateGraph(BAState)
    graph.add_node("retrieve_similar", retrieve_similar)
    graph.add_node("extract_requirements", extract_requirements)
    graph.add_node("synthesize_draft", synthesize_draft)
    graph.add_node("self_critique", self_critique)

    graph.add_edge(START, "retrieve_similar")
    graph.add_edge("retrieve_similar", "extract_requirements")
    graph.add_edge("extract_requirements", "synthesize_draft")
    graph.add_edge("synthesize_draft", "self_critique")
    graph.add_conditional_edges(
        "self_critique",
        _route_after_critique,
        {"synthesize_draft": "synthesize_draft", END: END},
    )
    return graph.compile()


def _get_client() -> claude_client_mod.ClaudeClient:
    """Construct a fresh ClaudeClient per call so tests can monkey-patch the module."""
    return claude_client_mod.ClaudeClient()


async def run_ba_agent(input_req: BARequirements) -> BusinessRequirementsDraft:
    """Entrypoint — run the BA graph and return the final draft (empty if LLM failed)."""
    compiled = _build_graph()
    initial: BAState = {"input_req": input_req, "iteration": 0}
    final_state: BAState = await compiled.ainvoke(initial)  # type: ignore[assignment]

    draft = final_state.get("draft")
    if draft is not None:
        return draft

    logger.error(
        "ba_agent.no_draft bid_id=%s err=%s",
        input_req.bid_id,
        final_state.get("error"),
    )
    return BusinessRequirementsDraft(
        bid_id=input_req.bid_id,
        executive_summary="",
        business_objectives=[],
        scope={"in_scope": [], "out_of_scope": []},
        functional_requirements=[],
        assumptions=[],
        constraints=list(input_req.constraints),
        success_criteria=[],
        risks=[],
        similar_projects=[],
        confidence=0.0,
        sources=[],
    )
