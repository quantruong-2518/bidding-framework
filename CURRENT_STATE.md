# CURRENT STATE — AI Bidding Framework

> File này dùng để track tiến độ. Mỗi conversation mới đọc file này trước.
> Cập nhật mỗi khi hoàn thành 1 task.

## Last Updated: 2026-04-18 (Phase 2.5 delivery — Conv-5 solo)

## Overall Status: PHASE 2 COMPLETE (all 7 sub-tasks) — next = Phase 3 (production hardening)

## >>> NEXT ACTION <<<
**Phase 3.5 — Langfuse observability (solo).** Detailed plan locked in memory `project_phase_3_5_detailed_plan.md`. Self-hosted Langfuse under Docker `profiles: ["observability"]`; wraps `ClaudeClient.generate` + `generate_stream` via `_CURRENT_LLM_SPAN` ContextVar; `trace_id = str(bid_id)` convention so every activity adds spans to the same trace without workflow-side coordination. **12 locked decisions, 21-step order, ~500 LOC, $0.** Observability-first ordering: instrument BEFORE user turns on real LLM, so first real tokens have full traces.

**Alternative pair option:** 3.5 + 3.1 (Jinja proposal templates, ~800 LOC) — orthogonal, both $0. Split only if context budget allows.

**Deferred (external dep):**
- Live-LLM smoke — needs `ANTHROPIC_API_KEY` in `src/.env`; rebuild both `ai-service` + `ai-worker`; `pytest -m integration -v`; watch `agent_token` events over WS + Langfuse traces (once 3.5 lands).
- 3.2 Full RBAC — Keycloak realm `bidding` provisioning (`bidding-realm.json` + `--import-realm`).
- 3.6 K8s migration / 3.7 Load testing — need cluster + traffic profile.

### Phase 2.5 Delivery Summary (2026-04-18, Conv-5 solo)
**Scope:** real-time agent token streaming + per-phase `state_completed` events + frontend `AgentStreamPanel`. All on the existing Redis pub/sub + socket.io fanout — zero new infra. Deterministic-first: zero `agent_token` publishes when `ANTHROPIC_API_KEY` absent; `state_completed` always fires.

**New files (ai-service):**
- `agents/stream_publisher.py` — `TokenPublisher` with throttled Redis PUBLISH (150 ms / 200 chars), `stream_context` asynccontextmanager, `_CURRENT_PUBLISHER` ContextVar. Best-effort (swallows Redis errors).
- `agents/_streaming.py` — `call_llm(client, *, node_name, ...)` helper: dispatches to `generate_stream` when publisher bound, else `generate`. Single-source for BA/SA/Domain node calls.
- `activities/state_transition.py` — `state_transition_activity` best-effort notify; payload `{type:"state_completed", state, profile, artifact_keys, occurred_at}`.
- `tests/test_stream_publisher.py` (7 tests), `tests/test_state_transition_activity.py` (3 tests), `tests/test_ba_agent_streaming.py` (4 tests — BA + SA + Domain symmetric coverage + BA fallthrough), `tests/test_workflow_stream_events.py` (2 tests).

**Modified (ai-service):**
- `tools/claude_client.py` — new `generate_stream(..., on_token)` method using Anthropic `messages.stream`. Existing `generate` untouched. `on_token` errors logged + swallowed.
- `agents/ba_agent.py`, `agents/sa_agent.py`, `agents/domain_agent.py` — each swapped its 3 `client.generate(...)` call sites (Haiku extract/classify/tag + Sonnet synthesize + Sonnet critique) for `call_llm(..., node_name=...)`. Retrieve node (Qdrant) NOT streamed.
- `activities/ba_analysis.py`, `activities/sa_analysis.py`, `activities/domain_mining.py` — inside the `if get_claude_settings().api_key` branch, instantiate `TokenPublisher(bid_id, agent, attempt=activity.info().attempt)` + `async with stream_context(pub): ...` + `aclose` in `finally`. Stub-fallback branch unchanged (no publisher, no tokens).
- `workflows/bid_workflow.py` — new `_PHASE_ARTIFACT_KEYS` declarative map, `_notify_state_transition(phase, keys)` helper (best-effort, 10s timeout, 1 attempt), `_complete_phase(phase)` wrapper (snapshot → notify order for read-your-writes), `run()` swaps every `await self._snapshot_workspace(X)` for `await self._complete_phase(X)`. Removed duplicate terminal `S11_DONE` snapshot (previously fired twice).
- `worker.py` — registers `state_transition_activity`.
- `tests/conftest.py` — new autouse fixture `_stub_redis_publish` monkeypatches `aioredis.from_url` across `activities.notify`, `activities.state_transition`, `agents.stream_publisher` so unit tests observe publishes without a real Redis. Exposes `_RedisCapture.events_of_type(t)` helper.
- `tests/test_workflow.py::_ALL_ACTIVITIES` — adds `state_transition_activity`.
- `tests/test_claude_client.py` — 3 new tests (stream forwards deltas, no-callback drains, on_token error swallowed).

**New files (frontend):**
- `components/workflow/agent-stream-panel.tsx` — collapsible panel (BA/SA/Domain label + node label + done/streaming badge + typewriter pre block). Renders idle state when stream is null.
- `__tests__/use-bid-events-stream.test.ts` (9 tests: 5 `applyToken` pure-function + 4 hook scenarios including 150 ms throttle, state_transitions buffering, bid-id switch reset, backwards-compat with `approval_needed`).
- `__tests__/agent-stream-panel.test.tsx` (3 tests).

**Modified (frontend):**
- `lib/ws/use-bid-events.ts` — extended `BidEventState` with `agentStreams: Record<AgentName, AgentStreamState | null>` + `stateTransitions: StateCompletedEvent[]`. Ref-based buffer + 150 ms throttled setState (`FLUSH_INTERVAL_MS`). Pure `applyToken` function handles attempt-dedup + node-reset + out-of-order seq drop. Transitions capped at 50. Buffer resets on bid-id change.
- `components/workflow/state-detail.tsx` — props extend with `agentStreams`; when `currentState === 'S3'` and selected is S3a/b/c, renders `<AgentStreamPanel>` above the existing artifact panel.
- `app/(authed)/bids/[id]/page.tsx` — pipes `agentStreams` from `useBidEvents` into `<StateDetail>`.

**NO CHANGES (by design, per D1):**
- `api-gateway/src/gateway/events.gateway.ts` — existing `relayToRoom` already fans out any Redis payload verbatim; new event types ride the same channel + same `bid.event` WS message.
- `api-gateway/src/redis/redis.service.ts` — no new methods needed.

**Contract tables (Redis payloads on `bid.events.channel.{bid_id}`):**

| type | fields |
|---|---|
| `agent_token` (new) | `agent ∈ {ba,sa,domain}`, `node`, `attempt`, `seq`, `text_delta`, `done` |
| `state_completed` (new) | `state` (e.g. `"S4_DONE"`), `profile`, `artifact_keys: string[]`, `occurred_at` ISO8601 |
| `approval_needed` (unchanged, Phase 2.4) | `state`, `workflow_id`, `round`, `reviewer_index`, `reviewer_count`, `profile` |

**Tests at delivery:** **97/97 pytest** (78 pre-existing + 7 publisher + 3 state_transition + 2 workflow events + 3 claude streaming + 4 agent streaming: BA+SA+Domain symmetric + fallthrough); 1 integration test correctly deselected. **17/17 Jest** (NestJS untouched). **41/41 vitest** (29 pre + 9 hook streaming + 3 panel). `tsc --noEmit` clean; `next build` succeeds.

**Live smoke:** NOT yet run in this conversation — Docker daemon not accessible. Runbook (carry forward to next conv):
```bash
# Rebuild BOTH images (per project_docker_image_split.md)
cd src && docker compose up -d --build ai-service ai-worker
docker compose restart ai-worker

# Without key — expect state_completed events, zero agent_token
curl -X POST http://localhost:8001/workflows/bid/start-from-card -H 'Content-Type: application/json' -d '{...}' | jq .workflow_id
# approve triage + review signals, watch `docker exec bid-redis redis-cli PSUBSCRIBE 'bid.events.channel.*'`
# Should see ~12 state_completed payloads (Bid-M); 0 agent_token.

# With key — expect both
# add ANTHROPIC_API_KEY to src/.env → docker compose up --build -d ai-service ai-worker
# Same start + signal flow; expect bursts of agent_token events during S3.
# Run the gated integration test:
docker run --rm --network bid-framework_default -v "$PWD/ai-service/tests:/app/tests:ro" \
  -e ANTHROPIC_API_KEY=... bid-framework-ai-service sh -c "pip install -q pytest pytest-asyncio && pytest -m integration -v"
```

**Known gaps carried to Phase 3:**
- SSE endpoint parity (deferred — socket.io already carries both streams; add SSE only if a non-browser consumer needs it).
- Token persistence via Redis XADD + MAXLEN (for late subscribers) — Phase 3.3 audit dashboard will want historical token streams.
- Langfuse trace around `generate_stream` — Phase 3.5.
- Per-tenant isolation before re-surfacing `kb-vault/bids/` in RAG — Phase 3 (multi-tenant tag contract).
- Frontend panel doesn't yet render `stateTransitions` as a live activity feed (buffer is populated but no UI consumer) — trivial to add in Phase 3 audit dashboard.

### Phase 2.6 + 2.4 Delivery Summary (2026-04-18, Conv-4 pair)
**Scope:** declarative profile pipeline (2.6) + real S9 human review gate with signal + loop-back + multi-round cap + WebSocket notification (2.4).

**Phase 2.6 (commit `8e96c17`):**
- `workflows/bid_workflow.py` — `_PROFILE_PIPELINE: dict[BidProfile, tuple[str,...]]` + `_STATE_DISPATCH_MAP`; `run()` now iterates the active profile's pipeline.
- Bid-S = `(S0, S1, S2, S3, S4, S6, S8, S9, S10, S11)` — skips S3c (via scoping re-route, pre-existing), S5 Solution Design, and S7 Commercial. Bid-M/L/XL = full 12-state pipeline; XL logs `XL_PARITY_PENDING` (S3d/S3e deferred to Phase 3).
- `S9_BLOCKED` added as terminal in `WorkflowState` literal + frontend `state-palette.ts` (danger tone) + `workflow-graph.tsx::mainOrderForCompare`.
- `AssemblyInput.hld` / `AssemblyInput.pricing` now `| None`; `assembly.py` null-guards both with Bid-S fallback text. `WBSInput.hld` likewise optional.
- `tests/conftest.py::_compress_gate_timeouts` autouse fixture compresses `HUMAN_GATE_TIMEOUT` / `ACTIVITY_TIMEOUT` / `S3_ACTIVITY_TIMEOUT` / `_S9_TIMEOUT` to 5s for non-integration tests.
- `tests/test_workflow_profile_routing.py` — 4 tests (Bid-S/M/L/XL).

**Phase 2.4 (commit below):**
- `workflows/models.py` — new `HumanReviewSignal`, `LoopBack` DTOs; `BidState.loop_back_history` field.
- `workflows/bid_workflow.py` — `@workflow.signal("human_review_decision")` handler appends to a FIFO queue (`_review_signals` + `_review_consumed` cursor) so pre-delivered signals aren't dropped by `self._review_signal = None` resets. `_run_s9_review_gate` runs pre-human `review_activity` then iterates per-profile reviewer count (`_S9_REVIEWER_COUNT = {S:1, M:1, L:3, XL:5}`); per-profile timeout (`_S9_TIMEOUT`, 72h / 120h XL). Any REJECT / CHANGES_REQUESTED short-circuits remaining reviewers in the round. 3-round cap terminates at `S9_BLOCKED`. `_route_on_changes_requested` picks earliest target from `_LOOP_BACK_ORDER = ("S2","S5","S6","S8")`, falls forward to nearest pipeline-resident state on Bid-S (e.g. `target=S5` falls forward to S6), clears downstream artifacts via declarative `_ARTIFACT_CLEANUP`.
- `activities/notify.py` (new) — `notify_approval_needed_activity` PUBLISHes `{type:"approval_needed",...}` to `bid.events.channel.<bid_id>` via `redis.asyncio`; wrapped in try/except so workflow never fails on Redis outage.
- `activities/review.py` — renamed to `_pre_human_review_impl` + `review_activity` wrapper; same consistency-check derivation but verdict explicitly tagged `phase-2.4-pre-human`.
- `workflows/router.py` — `POST /workflows/bid/{wf}/review-signal`.
- `api-gateway/src/workflows/review-signal.dto.ts` (new) — class-validator DTO for `verdict / reviewer / reviewerRole / comments / notes`.
- `workflows.service.ts::sendReviewSignal` — camelCase → snake_case transform; 409 CONFLICT if current_state ≠ S9 before forwarding.
- `workflows.controller.ts` — `POST review-signal` gated `@Roles('admin','bid_manager','qc','sa','domain_expert','solution_lead')` (new roles added to `roles.decorator.ts`).
- `frontend/components/bids/review-gate-panel.tsx` (new) — react-hook-form panel mirroring `TriageReviewPanel` shape; repeatable `comments[]` (section / severity / target_state); mounts at `currentState === 'S9'`.
- `frontend/lib/ws/use-bid-events.ts` — adds `approvalNeeded` state from `bid.event.type === 'approval_needed'` payload.
- Bid detail page renders `ReviewGatePanel` at S9 + `S9_BLOCKED` banner.

**New / modified files:**
- ai-service new: `activities/notify.py`, `tests/test_workflow_profile_routing.py`, `tests/test_workflow_review_gate.py`.
- ai-service modified: `workflows/base.py`, `workflows/models.py`, `workflows/artifacts.py`, `workflows/bid_workflow.py`, `workflows/router.py`, `activities/assembly.py`, `activities/review.py`, `worker.py`, `tests/conftest.py`, `tests/test_workflow.py`.
- api-gateway new: `src/workflows/review-signal.dto.ts`.
- api-gateway modified: `src/workflows/workflows.controller.ts`, `src/workflows/workflows.service.ts`, `src/auth/roles.decorator.ts`, `test/workflows.controller.spec.ts`.
- frontend new: `components/bids/review-gate-panel.tsx`, `__tests__/review-gate-panel.test.tsx`.
- frontend modified: `lib/api/types.ts`, `lib/api/bids.ts`, `lib/hooks/use-bids.ts`, `lib/ws/use-bid-events.ts`, `lib/utils/state-palette.ts`, `components/workflow/workflow-graph.tsx`, `app/(authed)/bids/[id]/page.tsx`, `__tests__/state-palette.test.ts`.
- docs: `docs/states/STATE_MACHINE.md` state matrix column flipped to "Status (2.6)" + SKIP (live) on S3c/S5/S7 for Bid-S + S9 row upgraded to "REAL (signal + loop-back)".

**Tests:** 78 pytest (70 + 8 new review-gate) + 4 new profile routing already counted; 17 Jest (14 + 3 new review-signal specs); 29 vitest (27 + 2 new review-gate-panel tests). All green; 1 integration test deselected.

**Live HTTP smoke:** not re-run (needs rebuilt ai-service + ai-worker images to pick up workflow bytecode; see `project_docker_image_split.md`). Recommended runbook: see plan step 31 in memory `project_phase_2_4_2_6_detailed_plan.md`.

### Phase 2.7 Delivery Summary (2026-04-18)
**Scope:** per-bid Obsidian workspace under `kb-vault/bids/{bid_id}/`. `workspace_snapshot_activity` fires after every workflow phase; writes are best-effort (bid completion > vault completeness).

**Design delta:** flat layout (`NN-<phase>.md` + single `09-reviews/` subfolder) instead of 11 nested phase dirs — better Obsidian file-tree UX. `kind: bid_output` frontmatter tags every file. Vault NOT re-ingested into Qdrant — Phase 3 adds multi-tenant isolation before enabling RAG over prior bids.

**New files:** `src/ai-service/kb_writer/{__init__,models,templates,bid_workspace}.py`; `activities/bid_workspace.py`; `tests/test_kb_writer.py` (5 tests); `tests/test_bid_workspace.py` (4 tests, tmp_path).

**Modified:** `workflows/bid_workflow.py` (11 snapshot call sites + `_snapshot_workspace` helper); `worker.py` (register workspace activity); `tests/test_workflow.py` (add to `_ALL_ACTIVITIES`); `tests/conftest.py` (`_sandbox_kb_vault` autouse → `KB_VAULT_PATH` per-test tmp).

**Tests:** 66 pytest (57 + 9 new), 14 Jest, 25 vitest — all green.

### Phase 2.3 Delivery Summary (2026-04-17)
**Scope:** upload PDF/DOCX RFP → ParsedRFP → suggested BidCard pre-fill. No LLM, no new Docker service.

**Design delta:** swapped Unstructured.io (1.5GB RAM container) for pypdf + python-docx (~1MB deps, pure Python). `parsers/` abstraction keeps the option open to plug Unstructured.io back in for OCR/complex-tables in Phase 3.

**New files:** `src/ai-service/parsers/{__init__,models,pypdf_adapter,docx_adapter,rfp_extractor}.py`; `tests/test_parsers.py` (13 tests); `src/api-gateway/src/parsers/{parsers.module,controller,service}.ts`; `test/parsers.controller.spec.ts` (3 tests); `src/frontend/lib/api/parsers.ts`; `src/frontend/components/bids/{rfp-upload,new-bid-shell}.tsx`.

**Modified:** `src/ai-service/pyproject.toml` (pypdf + python-docx + python-frontmatter deps); `workflows/router.py` (POST /workflows/bid/parse-rfp); `src/api-gateway/src/app.module.ts` (mount ParsersModule); `src/frontend/components/bids/create-bid-form.tsx` (accepts initialValues + resetToken props); `app/(authed)/bids/new/page.tsx` (uses NewBidShell).

**Tests:** 57 pytest (44 + 13 new), 14/14 Jest (11 + 3 new), 25/25 vitest, tsc + next build clean.

### Live after Phase 2.1 (what a dev can run today)
- `cd src && docker compose up --build -d` → **10** services healthy (~60–120s cold start)
- Frontend at `http://localhost:3001` → Demo-mode login renders dashboard + ReactFlow DAG with artifact panels for all 11 states
- Temporal UI at `http://localhost:8088`
- ai-service direct API at `http://localhost:8001/docs` (Swagger) — `/workflows/bid/*` endpoints walk the full S0→S11_DONE pipeline
- NestJS api-gateway at `http://localhost:3000` — new `GET /bids/:id/workflow/artifacts/:type` endpoint (JWT-gated, 14 artifact keys)
- Keycloak admin at `http://localhost:8080` (admin/admin) — realm `bidding` not yet provisioned (Phase 1.x), so authenticated flows need a pasted JWT or realm import

### Phase 2.2 Delivery Summary (2026-04-17, deterministic-first path)
**Scope:** full code path for real LangGraph-backed S3a/b/c + heuristic S4 convergence. Shipped without `ANTHROPIC_API_KEY` via a per-activity fallback gate — each real activity wrapper checks `get_claude_settings().api_key` and falls back to the Phase 2.1 deterministic stub when absent. 44/44 pytest pass (33 pre-existing + 11 new).

**Files added:**
- `src/ai-service/agents/prompts/sa_agent.py` + `agents/sa_agent.py` — Haiku classify + Sonnet synth/critique; LangGraph 4-node graph mirrors BA pattern (retrieve → classify → synth → critique → loop-on-low-confidence)
- `src/ai-service/agents/prompts/domain_agent.py` + `agents/domain_agent.py` — same shape, Haiku tags + Sonnet compliance + practices + glossary
- `src/ai-service/activities/sa_analysis.py` + `activities/domain_mining.py` — Temporal wrappers with heartbeats + stub-fallback gate
- `src/ai-service/tests/test_sa_agent.py` (3), `tests/test_domain_agent.py` (3), `tests/test_convergence.py` (5), `tests/test_workflow_integration.py` (1, gated)

**Files modified:**
- `src/ai-service/agents/models.py` — deleted `BARequirements`; BA agent now consumes shared `StreamInput` DTO (Q1 unification)
- `src/ai-service/agents/ba_agent.py` — input type rename only
- `src/ai-service/activities/ba_analysis.py` — input rename + same stub-fallback gate as SA/Domain
- `src/ai-service/activities/convergence.py` — 3 heuristic conflict rules (API-layer mismatch, compliance-gap, NFR-field-presence); readiness = 0.40·ba + 0.35·sa + 0.25·domain with gate at 0.80; `build_convergence_report` pure function extracted for unit tests
- `src/ai-service/workflows/bid_workflow.py::_run_s3_streams` — real activity refs; S3 timeout bumped 5min→10min + 2min heartbeat
- `src/ai-service/worker.py` — real activities registered; stubs kept in codebase (callable via fallback) but out of registry
- `src/ai-service/tests/test_workflow.py` — registers real activities in `_ALL_ACTIVITIES`; tests stay LLM-free because conftest autouse scrubs the key
- `src/ai-service/tests/conftest.py` — new autouse fixture `_force_llm_fallback_by_default` scrubs `ANTHROPIC_API_KEY` + clears `get_claude_settings` cache for every non-integration test
- `src/ai-service/pyproject.toml` — `addopts = "-m 'not integration'"` + `integration` marker registered
- `docs/phases/PHASE_2_PLAN.md` — Task 2.2 DELIVERED block
- `src/ai-service/CLAUDE.md` — stub-vs-real wording updated

**Test results:**
- ai-service: **44/44 pytest pass** (33 pre-existing + 3 SA + 3 Domain + 5 Convergence); 1 integration test correctly deselected via `-m 'not integration'`
- api-gateway: untouched, still 11/11 Jest
- frontend: untouched, still 24/24 vitest
- Live HTTP smoke: **not yet re-run** — Phase 2.1 behaviour unchanged because every test env + the existing running worker both take the stub-fallback path. Rebuild `ai-service` + `ai-worker` images + set `ANTHROPIC_API_KEY` before smoke-testing real agents.

### Phase 2.1 Delivery Summary (2026-04-17)
**Scope:** Deterministic 11-state DAG end-to-end with all S3..S11 artifacts stubbed. No LLM calls — unblocks shippable milestone without `ANTHROPIC_API_KEY`.

**Files added:**
- `src/ai-service/workflows/base.py` — shared primitives (RequirementAtom, BidProfile, WorkflowState) — broke circular import
- `src/ai-service/workflows/artifacts.py` — 20+ Pydantic DTOs for S3b..S11 artifacts + activity inputs
- `src/ai-service/activities/stream_stubs.py` — `ba_analysis_stub_activity`, `sa_analysis_stub_activity`, `domain_mining_stub_activity`
- `src/ai-service/activities/{convergence,solution_design,wbs,commercial,assembly,review,submission,retrospective}.py` — 8 downstream stubs
- `src/api-gateway/src/workflows/workflows.controller.ts` — new `@Get('artifacts/:type')` handler; `ARTIFACT_KEYS` exported
- `src/frontend/components/workflow/state-detail.tsx` — rewrote to render all 14 artifact types (BA/SA/Domain/Convergence/HLD/WBS/Pricing/Proposal/Reviews/Submission/Retrospective) with compact summaries

**Files modified:**
- `src/ai-service/workflows/models.py` — `WorkflowState` now includes `S11_DONE`; `BidState` has 11 new artifact fields
- `src/ai-service/workflows/bid_workflow.py` — rewrote `run()` as S0→S11_DONE; S3 parallel via `asyncio.gather`; per-state `_run_sN_*` helpers; state machine extended
- `src/ai-service/worker.py` — registers 11 new activities (does NOT register `ba_analysis_activity` — stays dormant until Phase 2.2)
- `src/ai-service/tests/test_workflow.py` — approved path now expects `S11_DONE`; new test `test_workflow_full_pipeline_populates_all_artifacts` asserts every artifact field present
- `src/ai-service/agents/models.py` — `RequirementAtom` now imported from `workflows.base` (cycle break)
- `src/api-gateway/src/workflows/workflows.service.ts` — `getArtifact(bidId, key)` proxies to status + extracts field
- `src/api-gateway/test/workflows.controller.spec.ts` — 3 new specs (ok, unknown-key 400, missing-field 404)
- `src/frontend/lib/api/types.ts` — 14 new Phase 2.1 artifact interfaces mirror Python payload (snake_case)
- `src/frontend/lib/api/bids.ts` — `getWorkflowArtifact<T>(id, type)` helper
- `src/frontend/lib/utils/state-palette.ts` — `S11_DONE` added; tone = `done`
- `src/frontend/app/(authed)/bids/[id]/page.tsx` — `inferSelected` routes `S11_DONE` to `S11`

**Test results:**
- ai-service: **33/33 pytest pass** (32 from Phase 1 + 1 new full-pipeline E2E)
- api-gateway: **11/11 Jest specs pass** (8 existing + 3 new artifact endpoint specs)
- frontend: **24/24 vitest pass**, `tsc --noEmit` clean, `next build` succeeds
- Live HTTP: workflow started via `POST /workflows/bid/start-from-card` + approve signal reaches `S11_DONE` with all 11 artifacts populated (WBS total_effort_md=205, pricing.total ≈ $246k, submission confirmation SUB-xxxxxxxx)

### Phase 1 Hardening Pass (2026-04-17 PM)
Cold-start on a fresh host revealed 7 defects in the original Phase 1 delivery — all fixed and verified:

| # | File | Defect | Fix |
|---|---|---|---|
| 1 | `ai-service/pyproject.toml` | `python = "^3.12"` resolves `>=3.12,<4.0`, conflicts with `fastembed` (<3.13) → build fail | Narrowed to `python = ">=3.12,<3.13"` |
| 2 | `src/docker-compose.yml` temporal healthcheck | Used `sh /dev/tcp/...` — auto-setup image's `sh` lacks `/dev/tcp`, probe always fails | Switched to `tctl --address $(hostname):7233 cluster health \| grep -q SERVING` (127.0.0.1 wrong — Temporal binds to container IP) |
| 3 | `src/docker-compose.yml` keycloak healthcheck | Probed mgmt port 9000, but KC 24 doesn't expose separate mgmt port (25+ only) | Probe `/health/ready` on port 8080 |
| 4 | `src/frontend/Dockerfile` | Missing `ARG NEXT_PUBLIC_*` → Next.js inlines fallback `http://localhost:3001` → dashboard calls frontend instead of gateway → client-side crash | Added build ARGs + ENV; compose passes `args:` block |
| 5 | `src/docker-compose.yml` | No `ai-worker` service → Temporal task queue has no consumer → workflows accepted but never processed | Added `ai-worker` service running `python worker.py` reusing ai-service image |
| 6 | `ai-service/config/temporal.py` + `worker.py` | Default JSON converter loses pydantic type on `handle.query` round-trip (Pydantic v2 warning had been firing) | Wired `temporalio.contrib.pydantic.pydantic_data_converter` on both worker + client |
| 7 | `ai-service/agents/ba_agent.py` | Graph always loops when confidence < 0.5, even with empty KB — crashes BA tests and wastes LLM calls on RAG outage | `_route_after_critique` short-circuits to END when `retrieved` is empty (degraded mode) |
| 8 | `src/docker-compose.yml` ai-worker | Inherited ai-service image's HEALTHCHECK (probe HTTP :8001) but `worker.py` does not listen → container always reports `unhealthy` | `healthcheck: {disable: true}`; rely on `restart: unless-stopped` for liveness |

Also added: `./kb-vault` bind-mounted into ai-service + ai-worker at `/kb-vault` with `KB_VAULT_PATH=/kb-vault`, so `python -m ingestion` works out of the box.

### Phase 1 Verification Runbook (run these to confirm a clean state)
```bash
# 1. Cold start
cd src && docker compose up -d --build           # expect 10 services healthy
docker compose ps -a                              # all "Up … (healthy)"

# 2. Seed data
docker exec bid-ai-service python -m rag.seed                    # 61 chunks / 9 files
docker exec bid-ai-service python -m ingestion                   # 21 notes / 111 edges

# 3. Workflow E2E (no LLM required — stub deterministic S0→S1→S2)
curl -s -X POST http://localhost:8001/workflows/bid/start-from-card \
  -H 'Content-Type: application/json' \
  -d '{"client_name":"Verify","industry":"Banking","region":"SEA","deadline":"2026-12-31T00:00:00Z","scope_summary":"verify","technology_keywords":["go"],"estimated_profile":"M","requirements_raw":["x"]}'
# → {"workflow_id":"bid-<uuid>",...}
# Send approve signal:
curl -s -X POST http://localhost:8001/workflows/bid/<id>/triage-signal \
  -H 'Content-Type: application/json' -d '{"approved":true,"reviewer":"verify"}'
# Query:
curl -s http://localhost:8001/workflows/bid/<id> | jq .current_state  # → "S2_DONE"

# 4. Tests — all green after the hardening pass
# ai-service (32 tests) — tests/ is dockerignored; run via temp container with bind-mount
docker run --rm --network bid-framework_default \
  -v "$PWD/ai-service/tests:/app/tests:ro" \
  -e QDRANT_URL=http://qdrant:6333 -e TEMPORAL_HOST=temporal:7233 -e REDIS_URL=redis://redis:6379 \
  bid-framework-ai-service sh -c "pip install -q pytest pytest-asyncio && pytest -v"
# api-gateway (8 tests) — use test:e2e not default test (rootDir miss)
cd api-gateway && npm run test:e2e
# frontend (24 tests + typecheck + build)
cd ../frontend && npx vitest run && npx tsc --noEmit && npm run build
```

### Documentation refreshed (2026-04-17)
- `CURRENT_STATE.md` (this file) — Phase 1 complete, Next Action = Phase 2.1
- `docs/phases/PHASE_1_PLAN.md` — each task has a "DELIVERED" block + Phase 1 Delivered Summary (waves, test counts, contracts, known gaps)
- `docs/states/STATE_MACHINE.md` — state matrix annotated with Phase 1 impl status; implementation pointers table added
- `docs/architecture/SYSTEM_ARCHITECTURE.md` — "Phase 1 Implementation Map" appended (layer → files/containers + cross-service contracts)
- Sub-repo CLAUDE.md added for vibe coding with cwd inside any service:
  - `src/ai-service/CLAUDE.md`
  - `src/api-gateway/CLAUDE.md`
  - `src/frontend/CLAUDE.md`
  - `src/kb-vault/CLAUDE.md`

---

## Phase 1: Core Foundation (Weeks 1-4)

| # | Task | Status | Notes |
|---|---|---|---|
| 1.1 | Setup project structure + Docker Compose | DONE | 9 services, healthchecks wired, `docker compose config` clean |
| 1.2 | Temporal workflow: S0 + S1 + S2 | DONE | `bid_workflow.py` + intake/triage/scoping activities + FastAPI router + `/start-from-card` for UI-entered bids |
| 1.3 | 1 LangGraph agent (BA Agent) PoC | DONE | 4-node graph (retrieve→Haiku extract→Sonnet synth→Sonnet critique), prompt caching, activity wrapper ready. NOT yet registered in `worker.py` — wired in Phase 2.2 |
| 1.4 | Basic RAG: Qdrant + embedding pipeline | DONE | fastembed (bge-small 384d) + BM25 sparse → Qdrant RRF fusion + Cohere rerank fallback; 9 seed docs; idempotent UUID5 upserts |
| 1.5 | Obsidian KB vault + ingestion service | DONE | 20 notes / 5 doc_types / 81+ links; `IngestionService` with watchdog+polling fallback, hash cache, graph snapshot |
| 1.6 | NestJS API gateway + Keycloak auth | DONE | Bids CRUD + workflow proxy + WS gateway; JWKS-backed JWT guard + roles guard; realm provisioning deferred |
| 1.7 | Minimal Next.js frontend | DONE | App Router, zustand + TanStack Query + ReactFlow + socket.io; demo-mode login; tsc/vitest/build/lint green |

## Phase 2: Full Pipeline (Weeks 5-8)

| # | Task | Status | Notes |
|---|---|---|---|
| 2.1 | Complete 11-state DAG in Temporal | DONE | 11 deterministic stubs wired via asyncio.gather for S3; workflow reaches S11_DONE end-to-end |
| 2.2 | Parallel agent execution (S3a, S3b, S3c) | DONE (deterministic-first) | Real BA/SA/Domain LangGraph agents + heuristic S4 convergence shipped. Each activity falls back to its stub until `ANTHROPIC_API_KEY` is set. 44/44 pytest pass; 1 integration test deselected |
| 2.3 | Document parsing pipeline | DONE (pypdf MVP) | PDF + DOCX → ParsedRFP + BidCard suggestion. pypdf + python-docx (no Unstructured.io container); gateway proxy + frontend drop-zone; 13 new pytest + 3 new Jest |
| 2.7 | Bid workspace in Obsidian | DONE | Flat `kb-vault/bids/{bid_id}/NN-*.md` layout; `workspace_snapshot_activity` after each phase; 15 render funcs with `kind: bid_output` frontmatter; best-effort (never blocks bid). Re-ingestion deferred to Phase 3 |
| 2.4 | Human approval flow (Temporal signals) | DONE | Real S9 gate: `human_review_decision` signal, sequential multi-reviewer, earliest-target loop-back with artifact cleanup, 3-round cap → S9_BLOCKED; `notify_approval_needed_activity` WS broadcast |
| 2.5 | Real-time updates (SSE + WebSocket) | DONE | `TokenPublisher` (throttle 150 ms / 200 chars) + `stream_context` ContextVar → agents route through `ClaudeClient.generate_stream`; `state_transition_activity` after each phase. Frontend `AgentStreamPanel` + extended `useBidEvents`. 97 pytest, 41 vitest. |
| 2.6 | Bid Profile routing (S/M/L/XL) | DONE | `_PROFILE_PIPELINE` matrix; Bid-S skips S5/S7; assembly null-guards; XL logs parity-pending |

## Phase 3: Production Ready (Weeks 9-12)

| # | Task | Status | Notes |
|---|---|---|---|
| 3.1 | Document generation (proposal templates) | NOT STARTED | |
| 3.2 | Full RBAC per role | NOT STARTED | |
| 3.3 | Audit dashboard | NOT STARTED | |
| 3.4 | Retrospective module (S11) | NOT STARTED | |
| 3.5 | LLM observability (Langfuse) | NOT STARTED | |
| 3.6 | Kubernetes migration | NOT STARTED | |
| 3.7 | Performance optimization + load test | NOT STARTED | |

---

## Decisions Made

| Decision | Choice | Date | Reason |
|---|---|---|---|
| Orchestration | Temporal.io + LangGraph | 2026-04-17 | Temporal for durability, LangGraph for AI agents |
| LLM Strategy | Full Claude API (Sonnet + Haiku) | 2026-04-17 | Quality first, optimize cost via tiered routing + caching |
| Vector DB | Qdrant (primary) + pgvector (convenience) | 2026-04-17 | Hybrid search, self-hosted, enterprise filtering |
| API Gateway | NestJS (TypeScript) | 2026-04-17 | Auth, RBAC, WebSocket |
| AI Services | Python FastAPI + Temporal workers | 2026-04-17 | AI/ML ecosystem, LangGraph |
| Frontend | Next.js App Router + shadcn/ui + ReactFlow | 2026-04-17 | SSR, realtime, DAG visualization |
| Knowledge Workspace | Obsidian (Git sync) | 2026-04-17 | Free, markdown-based, [[links]] = knowledge graph |
| Doc Parsing | Unstructured.io (self-hosted) | 2026-04-17 | Best PDF/DOCX quality, open-source |
| Auth | Keycloak (self-hosted) | 2026-04-17 | Enterprise identity, SSO, free |
| Observability | Langfuse (self-hosted) | 2026-04-17 | Open-source thay LangSmith, $0 |
| Phase 1 Infra | Docker Compose on VPS | 2026-04-17 | K8s chưa cần, migrate Phase 3 |

## Open Questions

- [ ] Client nào dùng thử pilot?
- [ ] Data sovereignty requirements cụ thể?
- [ ] Existing KB data ở đâu? Format gì?
- [ ] Team size cho Phase 1 development?

## Known Gaps Carried Into Phase 3

Audited + pruned 2026-04-18 after Phase 2 closure. Stale entries removed:
~~`ba_analysis_activity` not registered~~ (registered since Phase 2.2);
~~Triage shape mismatch~~ (closed as part of Phase 2 audit — frontend `Triage`
now matches Python `TriageDecision`).

- **Keycloak realm `bidding` not provisioned** — `docker-compose.yml` runs `start-dev` without `--import-realm`; add `bidding-realm.json` and `--import-realm` flag before wiring real auth end-to-end. Phase 3.2 owns.
- **Api-gateway Jest `rootDir=src` only discovers `src/**/*.spec.ts`** — run `npm run test:e2e` (or move specs under `src/`) to include `test/*.spec.ts`. Unchanged convention; documented.
- **Postgres persistence for bids uses an in-memory Map** in `bids.service.ts` — swap for TypeORM/Prisma in Phase 3. `bidding_db` is empty (0 tables) — no migration yet.
- **CORS defaults to `*`** when `CORS_ORIGIN` unset — tighten before any shared-environment deploy.
- **ai-service `Dockerfile` `.dockerignore` excludes `tests/`** — pytest must run via bind-mount (`docker run --rm -v "$PWD/tests:/app/tests:ro" ...`) rather than `docker exec`. Consider a separate `Dockerfile.test` target in Phase 3.
- **`ANTHROPIC_API_KEY` not wired from `.env` by default** — `src/.env` not created by compose. Copy `.env.example` → `.env` and set the key before running any LLM-dependent flow (real BA/SA/Domain agents, Cohere rerank, Phase 2.5 token streams). S0–S11 run on deterministic stubs + fallback gate, need no key.
- **`ai-worker` uses a separate Docker image tag** (`bid-framework-ai-worker`) — when iterating on workflow/activity code, rebuild BOTH `ai-service` AND `ai-worker` images, then force-recreate the worker container. Runbook: see `memory/project_docker_image_split.md`. Was the #1 debug blocker in 2.1; recurred in 2.4/2.5 deliveries.
- **`kb-vault/bids/` NOT re-ingested into Qdrant** (Phase 2.7 carry-forward) — multi-tenant isolation required before prior-bid content surfaces to new-bid RAG. Phase 3 owns.
- **Live-LLM smoke for Phase 2.2 + 2.5 not yet run** — stub path is default; set `ANTHROPIC_API_KEY`, rebuild both images, run `pytest -m integration -v`. `ba_draft.executive_summary` no longer starts with `"Stub BA summary"` when live.
