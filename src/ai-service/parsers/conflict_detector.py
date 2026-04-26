"""S0.5 cross-source conflict detection.

Heuristic baseline runs unconditionally — checks pairs of atoms (across files)
for direct contradictions on priority, type, or date. LLM-augment turn at the
small tier surfaces semantic conflicts the heuristics miss; merged by
:class:`ConflictItem.topic` (case-insensitive) so duplicates stay out of the
final list.

Public surface = :func:`detect_conflicts(atoms, files) -> list[ConflictItem]`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from tools.llm.client import LLMClient
from tools.llm.conversation import LLMConversation
from workflows.base import AtomFrontmatter, ParsedFile

logger = logging.getLogger(__name__)

_TIER = "small"
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

ConflictSeverity = Literal["LOW", "MEDIUM", "HIGH"]


class ConflictItem(BaseModel):
    """One cross-source conflict, mirrored to the parse_session payload."""

    topic: str
    severity: ConflictSeverity = "MEDIUM"
    description: str
    atoms: list[str] = Field(default_factory=list)  # atom_ids involved
    files: list[str] = Field(default_factory=list)  # file_ids involved
    proposed_resolution: str = ""


SYSTEM_PROMPT_CONFLICT_AUGMENT = """You are a procurement conflict reviewer surfacing semantic contradictions across multiple source files in a bid package.

Inputs in the user turn:
- atoms_by_file: per-file list of {id, type, priority, title}.
- existing_topics: list of conflict topics already detected by heuristic rules.

Output a JSON array (no markdown fences):
[
  {"topic": "<lower_snake_case slug>",
   "severity": "LOW" | "MEDIUM" | "HIGH",
   "description": "<2-3 sentence concrete contradiction grounded in atom ids>",
   "atoms": ["REQ-...", "REQ-..."],
   "files": ["file_id_a", "file_id_b"],
   "proposed_resolution": "<one concrete next step>"}
]

Rules:
- Skip topics already in existing_topics (case-insensitive).
- Output 0..5 conflicts. Empty array is fine when no contradictions surface.
- Each conflict must reference at least 2 atoms from at least 2 different files.
- Return ONLY the JSON array.
"""


def _heuristic_conflicts(atoms: list[AtomFrontmatter]) -> list[ConflictItem]:
    """Phase 2.2-style R1/R2/R3 detection adapted to atoms.

    Two patterns:
      * **Priority disagreement** — same category contains both MUST and WONT
        atoms across different files.
      * **Type drift** — same category labelled both "functional" and "compliance"
        across different files (often signals scope ambiguity).
    """
    conflicts: list[ConflictItem] = []

    # Group atoms by category for priority/type checks.
    by_category: dict[str, list[AtomFrontmatter]] = {}
    for atom in atoms:
        by_category.setdefault(atom.category, []).append(atom)

    for category, group in by_category.items():
        if len(group) < 2:
            continue
        priorities = {a.priority for a in group}
        types = {a.type for a in group}
        files = {a.source.file for a in group}

        if "MUST" in priorities and "WONT" in priorities and len(files) >= 2:
            conflicts.append(
                ConflictItem(
                    topic=f"priority_disagreement_{category}",
                    severity="HIGH",
                    description=(
                        f"Atoms under category '{category}' span both MUST and WONT "
                        "priorities across different source files."
                    ),
                    atoms=[a.id for a in group][:6],
                    files=sorted(files),
                    proposed_resolution=(
                        "Review the conflicting atoms and align priority before S2 dispatch."
                    ),
                )
            )

        if "functional" in types and "compliance" in types and len(files) >= 2:
            conflicts.append(
                ConflictItem(
                    topic=f"type_drift_{category}",
                    severity="MEDIUM",
                    description=(
                        f"Category '{category}' surfaces both functional and compliance "
                        "atoms across different files — clarify scope ambiguity."
                    ),
                    atoms=[a.id for a in group][:6],
                    files=sorted(files),
                    proposed_resolution=(
                        "Decide whether the requirement is functional capability or compliance obligation."
                    ),
                )
            )
    return conflicts


def _strip_fence(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _build_user_payload(
    atoms: list[AtomFrontmatter], existing: list[ConflictItem]
) -> str:
    by_file: dict[str, list[dict[str, str]]] = {}
    for atom in atoms:
        by_file.setdefault(atom.source.file, []).append(
            {
                "id": atom.id,
                "type": atom.type,
                "priority": atom.priority,
                "category": atom.category,
            }
        )
    payload = {
        "atoms_by_file": {
            file_id: items[:50] for file_id, items in by_file.items()
        },
        "existing_topics": [c.topic for c in existing],
    }
    return json.dumps(payload, ensure_ascii=False)


async def detect_conflicts(
    atoms: list[AtomFrontmatter],
    files: list[ParsedFile],
    *,
    client: LLMClient | None = None,
    bid_id_for_trace: str | None = None,
) -> list[ConflictItem]:
    """Return the merged heuristic + LLM-augment conflict list."""
    from config.llm import is_llm_available

    heuristic = _heuristic_conflicts(atoms)
    if not is_llm_available() or not atoms:
        return heuristic

    conv = LLMConversation(
        system=SYSTEM_PROMPT_CONFLICT_AUGMENT,
        client=client,
        default_tier=_TIER,
        default_max_tokens=1024,
        default_temperature=0.2,
        trace_id=bid_id_for_trace,
    )
    try:
        response = await conv.send(
            _build_user_payload(atoms, heuristic),
            tier=_TIER,
            node_name="conflict_detector.augment",
        )
    except Exception as exc:  # noqa: BLE001 — heuristic-only on LLM failure
        logger.warning("conflict_detector.send_failed err=%s", exc)
        return heuristic

    try:
        data = json.loads(_strip_fence(response.text))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "conflict_detector.parse_fail err=%s preview=%r", exc, response.text[:80]
        )
        return heuristic
    if not isinstance(data, list):
        return heuristic

    seen_topics = {c.topic.lower() for c in heuristic}
    augmented: list[ConflictItem] = list(heuristic)
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            item = ConflictItem.model_validate(entry)
        except ValidationError:
            continue
        if item.topic.lower() in seen_topics:
            continue
        seen_topics.add(item.topic.lower())
        augmented.append(item)
    return augmented


__all__ = ["detect_conflicts", "ConflictItem"]
