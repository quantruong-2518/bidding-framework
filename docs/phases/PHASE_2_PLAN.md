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

## Task 2.4: Human Approval Flow — **DONE 2026-04-18**
- Temporal signals for approval/rejection
- Review UI in frontend (approve, reject with feedback, route to state)
- Notification system (email/webhook when approval needed)
- Timeout & escalation (configurable per bid profile)

### DELIVERED

**Scope shipped:** real S9 review gate replacing the Phase 2.1 auto-approve
stub. `human_review_decision` Temporal signal handler queues reviewer
verdicts; `_run_s9_review_gate` iterates the per-profile reviewer count
(S/M=1, L=3, XL=5), short-circuits on first non-APPROVED, aggregates
verdict, either advances the pipeline or loops back to the earliest
target (S2 / S5 / S6 / S8) declared in reviewer comments. 3-round cap
terminates at `S9_BLOCKED` (new WorkflowState literal). Per-profile
timeout (72h / 120h XL) terminates at `S9_BLOCKED` when no signal
arrives.

**Design deltas:**
- Signal storage = FIFO list + monotonic `_review_consumed` cursor (not
  single-slot `_review_signal = None` reset). Reason: pre-delivered
  signals must not be dropped by the reset, and multi-reviewer rounds
  need to consume in order anyway.
- `notify_approval_needed_activity` publishes `{type:"approval_needed"}`
  to `bid.events.channel.<bid_id>` via `redis.asyncio`. Wrapped in
  try/except so a Redis outage never fails the workflow. Existing
  `events.gateway.ts` relay picks it up — no new WebSocket channel.
- NestJS guards signal with `current_state === 'S9'` pre-check →
  returns 409 CONFLICT if the gate already resolved (double-submit
  protection).
- Artifact cleanup on loop-back is declarative (`_ARTIFACT_CLEANUP`
  whitelist) — choosing target S5 resets `_hld/_wbs/_pricing/_proposal`,
  target S2 resets the whole downstream chain.
- Roles `domain_expert` / `solution_lead` added to `AppRole` for L/XL
  reviewer authorisation.

**Files:** see `CURRENT_STATE.md` Phase 2.6 + 2.4 Delivery Summary.
**Tests:** 8 review-gate scenarios + 4 profile-routing scenarios + 3
new workflows.controller specs + 2 new review-gate-panel tests.

### Known gaps carried to Phase 3
- Email / Slack notification (WebSocket only for now).
- Parallel concurrent reviewer signatures (sequential today).
- Reviewer auto-escalation on timeout (terminal `S9_BLOCKED` today;
  ops must restart workflow).
- XL multi-gate parity (C-level approval after the L gate) — deferred.

## Task 2.5: Real-time Updates
- SSE for agent streaming (token-by-token output)
- WebSocket for workflow state transitions
- Redis Pub/Sub for Python workers -> NestJS -> Frontend

## Task 2.6: Bid Profile Routing — **DONE 2026-04-18**
- S/M/L/XL profile configuration
- Dynamic pipeline: skip/simplify states based on profile
- Profile-specific review gate configuration

### DELIVERED

**Scope shipped:** declarative `_PROFILE_PIPELINE: dict[BidProfile,
tuple[str,...]]` at the top of `bid_workflow.py`; `run()` iterates the
active profile's pipeline via a while-loop so Phase 2.4 loop-backs can
rewind the cursor.

**Profile matrix:**
- **Bid-S:** `(S0, S1, S2, S3, S4, S6, S8, S9, S10, S11)` — skips S3c
  (via scoping re-route, pre-existing), S5 Solution Design, and S7
  Commercial. `assembly.py` null-guards `hld=None` + `pricing=None`
  (executive summary emits "TBD", solution section falls back to SA
  tech-stack, commercial section notes deferred terms).
- **Bid-M / Bid-L:** full 12-state pipeline.
- **Bid-XL:** runs L pipeline; workflow logs
  `XL_PARITY_PENDING phase=2.6` at entry. S3d/S3e + C-level multi-gate
  deferred to Phase 3.

**Stability guards:** `tests/conftest.py::_compress_gate_timeouts`
autouse fixture shrinks `HUMAN_GATE_TIMEOUT`, `ACTIVITY_TIMEOUT`,
`S3_ACTIVITY_TIMEOUT`, and `_S9_TIMEOUT` to 5s for every non-integration
test so Temporal's time-skipping env settles fast.

**Files:** `workflows/base.py` (adds `S9_BLOCKED` literal), `workflows/bid_workflow.py`,
`activities/assembly.py`, `workflows/artifacts.py` (`hld/pricing` now
`| None`), `tests/test_workflow_profile_routing.py`,
`src/frontend/lib/utils/state-palette.ts`,
`src/frontend/components/workflow/workflow-graph.tsx`,
`docs/states/STATE_MACHINE.md`.

## Task 2.7: Bid Workspace in Obsidian — **DONE 2026-04-18**
- Auto-create bid folder structure when bid starts
- AI output writes to vault as markdown
- Bi-directional sync: vault changes -> re-index — *deferred to Phase 3 (multi-tenant isolation required)*

### DELIVERED

**Scope shipped:** every Temporal workflow phase emits a markdown snapshot of
the bid's current `BidState` into `<vault>/bids/<bid_id>/` via a new
best-effort `workspace_snapshot_activity`. Obsidian users get a live
view of the pipeline: one file per phase + a reviews subfolder for
multi-round gates + an `index.md` hub with wiki-links to every populated
artifact.

**Design delta from plan:** adopted a **flat** layout (`NN-<phase>.md` at
the bid root + a single `09-reviews/` subfolder) instead of 11 nested
phase directories. Reason: Obsidian's file-tree UX is materially better
when you don't have a directory per single file, and the `NN-` prefix
still sorts chronologically. The `kb-vault/bids/` tree is **not** re-ingested
into Qdrant for this phase — multi-tenant isolation needs more thought
(a client's in-progress bid shouldn't leak into another client's RAG
context). Phase 3 will revisit with proper access-control metadata.

**New files:**
- `src/ai-service/kb_writer/__init__.py`
- `src/ai-service/kb_writer/models.py` — `WorkspaceInput` (Temporal
  activity arg) + `WorkspaceReceipt` (return payload: files_written /
  files_skipped / errors).
- `src/ai-service/kb_writer/templates.py` — 15 render functions
  (bid_card, triage, scoping, ba, sa, domain, convergence, hld, wbs,
  pricing, proposal, review, submission, retrospective, index) using
  plain f-strings + `textwrap.dedent` + `python-frontmatter` to emit
  `kind: bid_output` + `bid_id` + `phase` + `artifact` + `generated_at`
  frontmatter on every file.
- `src/ai-service/kb_writer/bid_workspace.py` — `ensure_workspace`
  (idempotent folder scaffold) + `write_snapshot` (dispatches the
  appropriate renderer for each populated field in `BidState`, writes
  atomically via `tempfile.mkstemp` + `os.replace`, returns a receipt).
- `src/ai-service/activities/bid_workspace.py` — Temporal wrapper
  `workspace_snapshot_activity`; catches any exception and logs a warning
  rather than failing the workflow (bid completion > vault completeness).
- `src/ai-service/tests/test_kb_writer.py` — 5 tests covering
  frontmatter contract + content for BA / Convergence / Proposal / Index
  + bid-card sanity.
- `src/ai-service/tests/test_bid_workspace.py` — 4 tmp_path integration
  tests (scaffold dirs, full S11_DONE snapshot writes 15 files, skip
  None artifacts, repeat-call idempotency).

**Modified files:**
- `src/ai-service/workflows/bid_workflow.py` — calls
  `_snapshot_workspace(phase)` after every `_run_sN_*` helper (11 call
  sites + the S1_NO_BID terminal). The helper wraps
  `workflow.execute_activity(workspace_snapshot_activity, …)` with a
  30s `start_to_close_timeout`, 2-attempt retry policy, and a
  try/except that logs + swallows any failure.
- `src/ai-service/worker.py` — registers
  `workspace_snapshot_activity`.
- `src/ai-service/tests/test_workflow.py` — includes the workspace
  activity in `_ALL_ACTIVITIES` so the existing 5 workflow tests keep
  executing the full phase sequence.
- `src/ai-service/tests/conftest.py` — new autouse fixture
  `_sandbox_kb_vault` redirects `KB_VAULT_PATH` to `tmp_path` per test +
  clears `get_ingestion_settings` cache, keeping workflow tests hermetic.
- `src/ai-service/pyproject.toml` — `python-frontmatter ^1.1.0` dep
  (added alongside the Phase 2.3 pypdf deps).

**Test results:** 9 new pytest (5 kb_writer + 4 bid_workspace) green;
existing 57 pytest still green — total **66/66**. Integration test
correctly deselected.

**Known gaps carried forward:**
- `kb-vault/bids/` is excluded from ingestion. Phase 3 needs to add
  multi-tenant filtering (per-client `tenant_id` on Qdrant payload +
  on the kb_search filter contract) before these files can be safely
  surfaced to prior-bid RAG queries.
- Obsidian-side edits to `bids/<id>/*.md` are not round-tripped back
  into workflow state — files are render-only. If a reviewer amends
  `03-ba.md` directly, the next snapshot overwrites it. The
  retrospective activity is the planned bi-directional hook in
  Phase 3.4.
- No template customisation surface — f-strings live in code.
  Customer-branded proposal templates will move to Jinja in Phase 3.1.

---

## §5 — Docs follow-ups after Phase 2.1

- `docs/states/STATE_MACHINE.md` — annotate each S3..S11 row in the state
  matrix with `STUB` so reviewers know which states are deterministic vs real.
  Done 2026-04-17.
- `src/ai-service/CLAUDE.md` — clarify that `ba_analysis_activity` is dormant
  while `ba_analysis_stub_activity` is live. Done 2026-04-17.
- `src/frontend/CLAUDE.md` — mention `state-detail.tsx` artifact panels and
  the `/workflow/artifacts/:type` endpoint contract. Done 2026-04-17.
