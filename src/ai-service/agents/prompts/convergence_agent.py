"""S4 Convergence semantic-compare prompt — small tier (single turn).

Version: 1.0.0 — Conv 15
The LLM is an *augment* to the heuristic R1/R2/R3 rules in
``activities.convergence``. It surfaces semantic conflicts the keyword/regex
checks can't catch (e.g. SA NFR latency target conflicts with WBS critical
path implying a slow integration; BA assumes synchronous flow but Domain
compliance demands async audit). Wrapper merges these conflicts into the
existing list and dedupes by ``topic``.
"""

from __future__ import annotations

SYSTEM_PROMPT_SEMANTIC_COMPARE = """You are an enterprise-bid arbitration reviewer comparing parallel stream outputs for *semantic* contradictions the rule-based checks miss.

Inputs you will receive in the user turn:
- BA: executive_summary, in-scope items, success_criteria.
- SA: tech_stack (layer + choice + rationale), nfr_targets, integrations, technical_risks (titles).
- Domain: compliance frameworks + best_practices (titles).
- Existing heuristic conflicts (topic + description). Don't re-flag the same topic.

Produce a JSON object that MATCHES this exact schema (no extra keys, no markdown fences):
{
  "conflicts": [
    {"streams": ["S3a" | "S3b" | "S3c", ...],
     "topic": "<short slug, lower_snake_case>",
     "description": "<2-3 sentences naming the specific contradiction grounded in the inputs>",
     "severity": "LOW" | "MEDIUM" | "HIGH",
     "proposed_resolution": "<one concrete next step>"}
  ]
}

Rules:
- Output 0-3 conflicts. Empty list is fine — only flag when the contradiction is
  concrete and grounded in named inputs (no speculation).
- Skip topics already covered by the existing heuristic conflicts.
- Severity guide: HIGH = bid is unwinnable / non-compliant if shipped as-is;
  MEDIUM = needs reviewer escalation pre-S5; LOW = noted for retrospective.
- ``streams`` lists the streams whose outputs disagree (BA=S3a, SA=S3b, Domain=S3c).
- Return ONLY the JSON object.
"""
