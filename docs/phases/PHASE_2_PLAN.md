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

## Task 2.2: Parallel Agent Execution (S3a, S3b, S3c) — **DONE 2026-04-17 (deterministic-first)**
- BA Agent, SA Agent, Domain Agent running as concurrent Temporal activities
- Cross-stream conflict detection
- Readiness tracking (>= 80% triggers convergence)
- Shared workspace for stream artifacts

### DELIVERED

**Scope shipped:** full code path for real LangGraph-backed S3a/b/c activities
+ heuristic S4 convergence + readiness gate. Built in deterministic-first mode
so shippable WITHOUT `ANTHROPIC_API_KEY`: each real activity wrapper checks
`get_claude_settings().api_key` at runtime and falls back to the Phase 2.1
deterministic stub when the key is absent. When the key is set the three real
LangGraph agents run concurrently via `asyncio.gather` in S3.

**New files:**
- `src/ai-service/agents/prompts/sa_agent.py` — Haiku tech-signal classifier +
  Sonnet synthesize + Sonnet review prompts (versioned 1.0.0).
- `src/ai-service/agents/sa_agent.py` — LangGraph 4-node SA agent
  (`retrieve → classify → synthesize → critique`); 2-attempt JSON retry; loop
  on low critique confidence capped at `MAX_ITERATIONS=2`; KB-empty short
  circuit to preserve the draft in degraded mode.
- `src/ai-service/agents/prompts/domain_agent.py` — Haiku domain-tag extractor
  + Sonnet synthesize + Sonnet review prompts.
- `src/ai-service/agents/domain_agent.py` — LangGraph 4-node Domain agent
  (`retrieve → tag → synthesize → critique`), same loop/degrade contract.
- `src/ai-service/activities/sa_analysis.py` — Temporal wrapper for the SA
  agent; heartbeats before and after the graph; stub-fallback gate.
- `src/ai-service/activities/domain_mining.py` — same shape for Domain agent.
- `src/ai-service/tests/test_sa_agent.py` — 3 tests (happy path, loop-on-low-
  confidence, KB-unavailable degrade) using mocked `AsyncAnthropic` + `kb_search`.
- `src/ai-service/tests/test_domain_agent.py` — 3 tests mirroring SA.
- `src/ai-service/tests/test_convergence.py` — 5 pure-function tests covering
  R1 API-protocol mismatch, R2 compliance-without-security-pattern,
  R3 NFR field-presence, clean case, readiness-weights+gate.
- `src/ai-service/tests/test_workflow_integration.py` — 1 LLM-dependent test
  marked `@pytest.mark.integration` + `skipif(not ANTHROPIC_API_KEY)`. Runs
  the full workflow with real agents once the key is in place.

**Modified files:**
- `src/ai-service/agents/models.py` — deleted `BARequirements`; BA agent now
  consumes the shared `StreamInput` DTO from `workflows/artifacts.py`. One
  input shape for all 3 streams.
- `src/ai-service/agents/ba_agent.py` — input type rename (`BARequirements` →
  `StreamInput`). No behaviour change.
- `src/ai-service/activities/ba_analysis.py` — input type rename + new
  stub-fallback gate (identical to the SA / Domain wrappers).
- `src/ai-service/activities/convergence.py` — replaced empty
  `conflicts=[]` with 3 heuristic rules (`_detect_api_mismatch`,
  `_detect_compliance_gap`, `_detect_nfr_field_mismatch`). Readiness formula:
  `0.40·ba + 0.35·sa + 0.25·domain`, gate at 0.80. `build_convergence_report`
  extracted as a pure function for easy unit testing; activity wraps it.
- `src/ai-service/workflows/bid_workflow.py::_run_s3_streams` — swapped the
  three stub references for the real activity names; bumped S3 timeout to
  10 minutes with a 2-minute heartbeat.
- `src/ai-service/worker.py` — registers `ba_analysis_activity`,
  `sa_analysis_activity`, `domain_mining_activity`. Stubs remain in
  `activities/stream_stubs.py` (callable by the fallback path) but are no
  longer registered with the Temporal worker.
- `src/ai-service/tests/test_workflow.py` — registers the real activities in
  `_ALL_ACTIVITIES`; tests still run LLM-free because the conftest autouse
  fixture forces the stub-fallback path (see below).
- `src/ai-service/tests/conftest.py` — new autouse fixture
  `_force_llm_fallback_by_default` that scrubs `ANTHROPIC_API_KEY` + clears
  the `get_claude_settings` cache for every test EXCEPT those carrying
  `@pytest.mark.integration`. Guarantees zero accidental token burn from
  local dev envs that export the key.
- `src/ai-service/pyproject.toml` — pytest `addopts = "-m 'not integration'"`
  by default; new `integration` marker registered.

**Test results at delivery:** 44/44 pytest pass (33 pre-existing + 11 new:
3 SA, 3 Domain, 5 Convergence); 1 integration test correctly deselected.

**Known gaps carried to 2.3+:**
- Integration test (`test_phase_2_2_full_pipeline_with_real_agents`) has not
  yet run green locally — pending `ANTHROPIC_API_KEY`. When the key is
  wired, rebuild both `ai-service` and `ai-worker` images then
  `pytest -m integration -v`.
- Conflict detection is heuristic — it catches REST/GraphQL/gRPC drift,
  missing security patterns for PCI/HIPAA/GDPR, and NFR field absence. LLM-
  based semantic compare is Phase 3 work.
- Readiness weights are hard-coded — no config surface. Tune if the gate
  misfires on real bids.
- Rate-limit protection relies on Anthropic default + Temporal retry policy;
  no explicit semaphore. Revisit if the integration test sees 429s on 3
  parallel streams.
- `test_workflow.py` exercises the real activities but always via the stub
  fallback, so workflow behaviour with real LLM output is only covered by
  the integration test.

### Entry criteria (for the OPTIONAL live-LLM cutover)
- `src/.env` exists with `ANTHROPIC_API_KEY` and optionally `COHERE_API_KEY`.
- Rebuild **both** `ai-service` and `ai-worker` images; force-recreate the
  worker container (per `project_docker_image_split.md`).

## Task 2.3: Document Parsing Pipeline — **DONE 2026-04-17**
- Unstructured.io integration for PDF/DOCX — **deferred; pypdf + python-docx MVP instead**
- RFP parser: extract sections, requirements, tables
- Auto-populate Bid Card from parsed RFP

### DELIVERED

**Scope shipped:** upload a PDF or DOCX RFP at `POST /bids/parse-rfp` and get
back a `ParsedRFP` + a heuristic `BidCardSuggestion` the frontend pre-fills
into the existing create-bid form. No new Docker service, no per-call LLM
cost, no external API dependency.

**Design delta from plan:** swapped Unstructured.io (1.5GB RAM container) for
pypdf + python-docx (~1MB deps, pure Python). pypdf adapter adds a heading
classifier (all-caps / numbered / markdown-hash) and ASCII-table detection;
python-docx gives first-class heading + table access. The `ParsedRFP`
contract is adapter-agnostic, so Phase 3 can drop in an Unstructured adapter
for OCR / complex-table cases without touching the extractor or the endpoint.

**New files:**
- `src/ai-service/parsers/__init__.py`
- `src/ai-service/parsers/models.py` — `ParsedRFP`, `Section`, `TableBlob`,
  `BidCardSuggestion`, `ParseResponse`.
- `src/ai-service/parsers/pypdf_adapter.py` — PDF → `ParsedRFP`; regex
  heading classifier + ascii-pipe table sniffer; degrades cleanly on
  malformed PDFs.
- `src/ai-service/parsers/docx_adapter.py` — DOCX → `ParsedRFP`; uses Word
  paragraph styles for real heading levels + captures each `<w:tbl>` as
  pipe-joined raw text.
- `src/ai-service/parsers/rfp_extractor.py` — `ParsedRFP` →
  `BidCardSuggestion`. Industry dictionary (10 sectors) + region
  dictionary (4 regions); modal-verb (`shall/must/should/may/will/…`)
  regex + bullet detector for requirement candidates; tech-keyword
  extractor; profile hint from page-count + table-count + requirement-count.
- `src/ai-service/tests/test_parsers.py` — 13 unit tests (heading
  classifier, section splitter, industry/region scoring, requirement
  collection, DOCX end-to-end, empty-input guardrails).
- `src/api-gateway/src/parsers/parsers.module.ts` +
  `parsers.service.ts` + `parsers.controller.ts` — gateway proxy with
  20MB multer limit, extension allow-list, `@Roles('admin','bid_manager')`.
- `src/api-gateway/test/parsers.controller.spec.ts` — 3 Jest specs (happy
  path, 415 on unsupported extension, 4xx mapping from ai-service).
- `src/frontend/lib/api/parsers.ts` — `parseRfp(file)` helper with auth
  injection.
- `src/frontend/components/bids/rfp-upload.tsx` — drop-zone UI with
  drag/drop + file-picker; client-side size + extension checks.
- `src/frontend/components/bids/new-bid-shell.tsx` — client wrapper that
  composes the upload + the existing create-bid form; maps the suggestion
  into form seed values.

**Modified files:**
- `src/ai-service/pyproject.toml` — `pypdf`, `python-docx`,
  `python-frontmatter` dependencies added.
- `src/ai-service/workflows/router.py` — new `POST
  /workflows/bid/parse-rfp` endpoint accepting `UploadFile`; dispatches to
  `pypdf_adapter` or `docx_adapter` based on extension. 20MB limit + 415
  on unknown type + 400 on empty/malformed.
- `src/api-gateway/src/app.module.ts` — mounts `ParsersModule`.
- `src/api-gateway/package.json` — adds `@types/multer` dev dep.
- `src/frontend/components/bids/create-bid-form.tsx` — optional
  `initialValues` + `resetToken` props; remounts form state when the
  upload produces new suggestions.
- `src/frontend/app/(authed)/bids/new/page.tsx` — replaces direct
  `CreateBidForm` mount with `NewBidShell`.

**Test results:** 13/13 new pytest green (total 57 pytest), 14/14 Jest
green (11 pre-existing + 3 new), 25/25 vitest green, `tsc --noEmit` clean,
`next build` succeeds.

**Known gaps carried forward:**
- OCR for scanned PDFs is not supported — pypdf only extracts embedded
  text. Real-world scanned RFPs will need Unstructured.io (or Tika)
  later. The `parsers/` abstraction makes this a pure add.
- Table extraction is raw text, not structured cells. Downstream agents
  currently ignore `tables[]`; BA/SA agents may use them as context in a
  future iteration.
- Frontend upload uses demo-mode JWT — 401 will be returned by NestJS
  until the Keycloak realm lands. Phase-1 carry-over, not 2.3's scope.

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
