# Phase 2: Full Pipeline (Weeks 5-8)

## Goal
Complete 11-state DAG, parallel agent execution, document parsing, human approval flow.

> **Conversation split (2026-04-17):** Phase 2 is delivered across ~5 conversations.
> 2.1 ships solo with deterministic stubs. 2.2 needs `ANTHROPIC_API_KEY`. 2.3+2.7
> pair (filesystem IO). 2.4+2.6 pair (gate mechanics). 2.5 last (streaming layer
> depends on 2.2). See `CURRENT_STATE.md` for per-task status and the user's
> memory record `project_phase_2_roadmap.md` for rationale.

---

## Task 2.1: Complete 11-state DAG in Temporal — **DONE 2026-04-17**
- Add states S3 through S11 to Temporal workflow
- Implement state transitions, feedback loops
- Conditional routing based on Bid Profile (S/M/L/XL) — *deferred to 2.6*

### DELIVERED

**Scope shipped:** deterministic 11-state DAG (S0→S11_DONE) end-to-end. No LLM
calls, no external dependencies beyond the Phase 1 stack. Unblocks shippable
milestone while `ANTHROPIC_API_KEY` is still unset. Bid-profile-conditional
skip/simplify deferred to 2.6; feedback loops (S9 reject → back to S8/S6/S5/S2)
deferred to 2.4.

**New files:**
- `src/ai-service/workflows/base.py` — shared primitives (`RequirementAtom`,
  `BidProfile`, `WorkflowState`, `TriageRecommendation`, `utcnow`). Sits at the
  bottom of the workflow-layer dependency graph to break a circular import
  between `workflows.models`, `workflows.artifacts`, and `agents.models`.
- `src/ai-service/workflows/artifacts.py` — 20+ Pydantic DTOs for S3b..S11
  artifacts + every activity input type. Re-exports `BusinessRequirementsDraft`
  from `agents.models` so downstream has a single import surface.
- `src/ai-service/activities/stream_stubs.py` — `ba_analysis_stub_activity`,
  `sa_analysis_stub_activity`, `domain_mining_stub_activity`. Each derives its
  output from the scoping atoms — confidence climbs with requirement count.
- `src/ai-service/activities/{convergence,solution_design,wbs,commercial,assembly,review,submission,retrospective}.py`
  — 8 downstream stubs, each depending only on upstream `BidState` fields so
  the DAG composes cleanly.
- `src/api-gateway/src/workflows/workflows.controller.ts` — new
  `@Get('artifacts/:type')` endpoint; `ARTIFACT_KEYS` exported (14 keys).
- `src/frontend/components/workflow/state-detail.tsx` — rewritten with a
  per-node artifact renderer (14 panels total, one per state + stream).

**Modified files:**
- `src/ai-service/workflows/models.py` — `WorkflowState` now includes
  `S11_DONE` terminal. `BidState` adds 11 optional artifact fields. Re-exports
  all primitives from `workflows.base` for backwards compatibility.
- `src/ai-service/workflows/bid_workflow.py` — `BidWorkflow.run()` rewritten
  as a sequence of `_run_sN_*` helpers. S3 uses `asyncio.gather` to dispatch
  the three stream activities concurrently. Terminal is `S11_DONE`.
- `src/ai-service/worker.py` — registers the 11 new stubs. Intentionally
  **does not** register `ba_analysis_activity` (the real LLM-backed BA agent)
  — that swap is Phase 2.2's job.
- `src/ai-service/tests/test_workflow.py` — approved-path test now expects
  `S11_DONE`. New test `test_workflow_full_pipeline_populates_all_artifacts`
  asserts every artifact field present + sanity-checks WBS total, pricing
  total, and submission confirmation id.
- `src/ai-service/agents/models.py` — imports `RequirementAtom` from
  `workflows.base` instead of `workflows.models` (cycle break).
- `src/api-gateway/src/workflows/workflows.service.ts` —
  `getArtifact(bidId, key)` proxies to status + extracts field; 404 when
  artifact is null (not yet produced by workflow).
- `src/api-gateway/test/workflows.controller.spec.ts` — 3 new specs.
- `src/frontend/lib/api/types.ts` — 14 new artifact interfaces mirror the
  Python payload shape (snake_case).
- `src/frontend/lib/api/bids.ts` — `getWorkflowArtifact<T>(id, type)` helper.
- `src/frontend/lib/utils/state-palette.ts` — `S11_DONE` added; tone=done.
- `src/frontend/components/workflow/workflow-graph.tsx` — short-circuits to
  "all done" when `current_state = S11_DONE` (previously marked every node
  pending because the terminal sat past the comparison array).
- `src/frontend/app/(authed)/bids/[id]/page.tsx` — `inferSelected` routes
  `S11_DONE` back to `S11` for the side-pane detail view.

**Test results at delivery:**
- ai-service: 33/33 pytest (32 Phase 1 + 1 new full-pipeline E2E)
- api-gateway: 11/11 Jest (8 existing + 3 new artifact endpoint specs)
- frontend: 25/25 vitest (+1 S11_DONE graph regression), `tsc --noEmit` clean,
  `next build` succeeds
- Live HTTP (no LLM key): start → approve triage → S11_DONE with all 11
  artifacts populated (WBS total ≈205 MD, pricing ≈$246k, submission
  confirmation `SUB-xxxxxxxx`, SHA-256 package checksum first 16 chars)

**Known gaps carried to 2.2+:**
- Review stub auto-approves but does **not** loop back on
  `CHANGES_REQUESTED` / `REJECTED`. STATE_MACHINE.md §Feedback Loops is not
  honoured yet. Phase 2.4 owns the real gate.
- `ba_analysis_activity` sits dormant. Phase 2.2 swaps the 3 stream stubs
  for real LangGraph agents (BA already built; SA + Domain still to build).
- No `S3_DONE` literal — workflow stays in `S3` during the parallel gather
  and moves directly to `S4`. If the UI ever needs a sampled "S3 finished"
  state, add `S3_DONE` alongside `S2_DONE`/`S11_DONE`.
- Stub confidence formula is monotonic in requirement count — a bid with
  many low-quality atoms scores higher than one with a few sharp atoms.
  Fine as a placeholder; real agents will compute from content.
- Sub-repo `CLAUDE.md` files do not yet document the artifact panels or the
  stub/real BA split — see §5 in this phase plan for the follow-ups.

## Task 2.2: Parallel Agent Execution (S3a, S3b, S3c) — **BLOCKED on `ANTHROPIC_API_KEY`**
- BA Agent, SA Agent, Domain Agent running as concurrent Temporal activities
- Cross-stream conflict detection
- Readiness tracking (>= 80% triggers convergence)
- Shared workspace for stream artifacts

### Entry criteria
- `src/.env` exists with `ANTHROPIC_API_KEY` (required) and optionally
  `COHERE_API_KEY` (better rerank; ~10–15% retrieval quality gain).
- Phase 2.1 merged — workflow wired with stub stream activities.

### Concrete work
1. `agents/sa_agent.py` + `agents/prompts/sa_agent.py` — mirror the BA
   4-node graph (`retrieve → Haiku extract → Sonnet synth → Sonnet critique`).
2. `agents/domain_agent.py` + `agents/prompts/domain_agent.py` — same pattern.
3. `activities/sa_analysis.py` + `activities/domain_mining.py` — Temporal
   wrappers following `ba_analysis.py` conventions (heartbeat on long calls).
4. `workflows/bid_workflow.py::_run_s3_streams` — swap the three
   `_stub_activity` references for the real activity names.
5. `worker.py` — register the 3 real activities; remove the 3 stubs (or keep
   under an `AI_STUB_MODE` env flag if we want a degraded-mode fallback).
6. `activities/convergence.py` — replace empty `conflicts=[]` with real
   cross-stream conflict detection. Compute readiness from artifact
   completeness, not from stub-declared confidence.
7. Unit tests per agent with mocked `AsyncAnthropic` (don't burn tokens in CI);
   one integration test gated by `ANTHROPIC_API_KEY` (skip if unset).

## Task 2.3: Document Parsing Pipeline
- Unstructured.io integration for PDF/DOCX
- RFP parser: extract sections, requirements, tables
- Auto-populate Bid Card from parsed RFP

## Task 2.4: Human Approval Flow
- Temporal signals for approval/rejection
- Review UI in frontend (approve, reject with feedback, route to state)
- Notification system (email/webhook when approval needed)
- Timeout & escalation (configurable per bid profile)

## Task 2.5: Real-time Updates
- SSE for agent streaming (token-by-token output)
- WebSocket for workflow state transitions
- Redis Pub/Sub for Python workers -> NestJS -> Frontend

## Task 2.6: Bid Profile Routing
- S/M/L/XL profile configuration
- Dynamic pipeline: skip/simplify states based on profile
- Profile-specific review gate configuration

## Task 2.7: Bid Workspace in Obsidian
- Auto-create bid folder structure when bid starts
- AI output writes to vault as markdown
- Bi-directional sync: vault changes -> re-index

---

## §5 — Docs follow-ups after Phase 2.1

- `docs/states/STATE_MACHINE.md` — annotate each S3..S11 row in the state
  matrix with `STUB` so reviewers know which states are deterministic vs real.
  Done 2026-04-17.
- `src/ai-service/CLAUDE.md` — clarify that `ba_analysis_activity` is dormant
  while `ba_analysis_stub_activity` is live. Done 2026-04-17.
- `src/frontend/CLAUDE.md` — mention `state-detail.tsx` artifact panels and
  the `/workflow/artifacts/:type` endpoint contract. Done 2026-04-17.
