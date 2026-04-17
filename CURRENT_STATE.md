# CURRENT STATE — AI Bidding Framework

> File này dùng để track tiến độ. Mỗi conversation mới đọc file này trước.
> Cập nhật mỗi khi hoàn thành 1 task.

## Last Updated: 2026-04-17 (Phase 2.2 delivery — deterministic-first)

## Overall Status: PHASE 2.2 COMPLETE (code) — live-LLM integration test pending `ANTHROPIC_API_KEY`

## >>> NEXT ACTION <<<
**Phase 2.3 + 2.7 (pair): Document parsing (Unstructured.io) + per-bid Obsidian workspace**
- Both tasks are filesystem IO, no LLM churn — natural pair per `project_phase_2_roadmap.md`.
- 2.3: Unstructured.io container + RFP → BidCard auto-populate; add `profiles: ["parse"]` to `docker-compose.yml`.
- 2.7: per-bid folder scaffold under `kb-vault/bids/<bid-id>/`; hook into `ingestion_service.py`.

**Optional intermediate step (live-LLM smoke for 2.2):**
- Drop `ANTHROPIC_API_KEY` into `src/.env`, `docker compose up --build -d ai-service ai-worker` (rebuild both — see `project_docker_image_split.md`).
- Run the gated integration test: `pytest -m integration -v` (exercises real BA/SA/Domain agents).
- Live HTTP smoke: start workflow, approve, query status — `ba_draft.executive_summary` should no longer start with `"Stub BA summary"`.

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
| 2.3 | Document parsing pipeline (Unstructured.io) | NOT STARTED | |
| 2.4 | Human approval flow (Temporal signals) | NOT STARTED | S1 triage signal already exists as pattern; extend to S9 review gate |
| 2.5 | Real-time updates (SSE + WebSocket) | NOT STARTED | Redis + socket.io scaffold in place; needs agent-stream integration |
| 2.6 | Bid Profile routing (S/M/L/XL) | NOT STARTED | Scoping already emits profile; workflow needs conditional skips |
| 2.7 | Bid workspace in Obsidian (per-bid folders) | NOT STARTED | Retrospective stub already emits `kb_updates` placeholder path |

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

## Known Gaps Carried Into Phase 2.2+

- Keycloak realm `bidding` not yet provisioned — `docker-compose.yml` runs `start-dev` without `--import-realm`; add `bidding-realm.json` and `--import-realm` flag before wiring real auth end-to-end
- `ba_analysis_activity` implemented but **not registered** in `worker.py` (by design — Phase 2.2 swaps the stream stub for this real activity once `ANTHROPIC_API_KEY` is set)
- Api-gateway Jest default `rootDir=src` only discovers `src/**/*.spec.ts`; run `npm run test:e2e` (or move specs under `src/`) to include `test/*.spec.ts`
- Postgres persistence for bids uses an in-memory Map in `bids.service.ts` — swap for TypeORM/Prisma in Phase 2. `bidding_db` is empty (0 tables) — no migration yet.
- CORS defaults to `*` when `CORS_ORIGIN` unset — tighten before any shared-environment deploy
- ai-service `Dockerfile` `.dockerignore` excludes `tests/` — pytest must run via bind-mount (`docker run --rm -v "$PWD/tests:/app/tests:ro" ...`) rather than `docker exec`. Consider a separate `Dockerfile.test` target in Phase 2.
- ANTHROPIC_API_KEY not wired from `.env` by default — `src/.env` not created by compose. Copy `.env.example` → `.env` and set the key before running any LLM-dependent flow (real BA/SA agents, Cohere rerank). S0–S11 currently run on deterministic stubs and need no key.
- **Frontend/Python Triage shape mismatch (pre-existing, unchanged in 2.1):** frontend `Triage.recommend` ('bid' | 'no-bid') + `confidence` does not match Python's `TriageDecision.recommendation` ('BID' | 'NO_BID') + `overall_score`. UI shows "pending" for real triage output. Fix in Phase 2.4 (human approval flow revisit).
- **ai-worker uses a separate Docker image tag (`bid-framework-ai-worker`)** — when iterating on workflow/activity code, rebuild BOTH `ai-service` AND `ai-worker` images, then force-recreate the worker container. Missing this step was the #1 debug blocker during 2.1 (worker silently runs stale workflow bytecode).
