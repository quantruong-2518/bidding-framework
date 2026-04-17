# CURRENT STATE — AI Bidding Framework

> File này dùng để track tiến độ. Mỗi conversation mới đọc file này trước.
> Cập nhật mỗi khi hoàn thành 1 task.

## Last Updated: 2026-04-17

## Overall Status: PHASE 1 COMPLETE — ready for Phase 2

## >>> NEXT ACTION <<<
**Phase 2.1: Extend Temporal DAG to full 11 states (S3 parallel streams → S11 retrospective)**
- Add activities `convergence.py` (S4), `solution_design.py` (S5), `wbs.py` (S6), `commercial.py` (S7), `assembly.py` (S8), `review.py` (S9), `submission.py` (S10), `retrospective.py` (S11)
- Register `ba_analysis_activity` (built in 1.3) + new `sa_analysis_activity` + `domain_mining_activity` in `worker.py`; dispatch S3a/b/c in parallel via `workflow.execute_activity` + `asyncio.gather`
- Extend `BidState` schema with `ba_draft`, `sa_draft`, `domain_notes`, `hld`, `wbs`, `pricing`, `proposal_package`, `reviews`
- Add NestJS endpoints `/bids/:id/artifacts/:type` + corresponding frontend panels
- See `docs/phases/PHASE_2_PLAN.md` for full scope

### Live in Phase 1 (what a dev can run today)
- `cd src && docker compose up --build -d` → **10** services healthy (~60–120s cold start; includes new `ai-worker`)
- Frontend at `http://localhost:3001` → Demo-mode login renders dashboard + ReactFlow DAG
- Temporal UI at `http://localhost:8088`
- ai-service direct API at `http://localhost:8001/docs` (Swagger)
- Keycloak admin at `http://localhost:8080` (admin/admin) — realm `bidding` not yet provisioned (Phase 1.x), so authenticated flows need a pasted JWT or realm import

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
| 2.1 | Complete 11-state DAG in Temporal | NOT STARTED | |
| 2.2 | Parallel agent execution (S3a, S3b, S3c) | NOT STARTED | |
| 2.3 | Document parsing pipeline (Unstructured.io) | NOT STARTED | |
| 2.4 | Human approval flow (Temporal signals) | NOT STARTED | |
| 2.5 | Real-time updates (SSE + WebSocket) | NOT STARTED | |
| 2.6 | Bid Profile routing (S/M/L/XL) | NOT STARTED | |
| 2.7 | Bid workspace in Obsidian (per-bid folders) | NOT STARTED | |

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

## Known Gaps Carried Into Phase 2

- Keycloak realm `bidding` not yet provisioned — `docker-compose.yml` runs `start-dev` without `--import-realm`; add `bidding-realm.json` and `--import-realm` flag before wiring real auth end-to-end
- `ba_analysis_activity` implemented but not registered in `worker.py` (by design — Phase 2.2 wires S3a/b/c in parallel)
- Api-gateway Jest default `rootDir=src` only discovers `src/**/*.spec.ts`; run `npm run test:e2e` (or move specs under `src/`) to include `test/*.spec.ts`
- Postgres persistence for bids uses an in-memory Map in `bids.service.ts` — swap for TypeORM/Prisma in Phase 2. `bidding_db` is empty (0 tables) — no migration yet.
- CORS defaults to `*` when `CORS_ORIGIN` unset — tighten before any shared-environment deploy
- ai-service `Dockerfile` `.dockerignore` excludes `tests/` — pytest must run via bind-mount (`docker run --rm -v "$PWD/tests:/app/tests:ro" ...`) rather than `docker exec`. Consider a separate `Dockerfile.test` target in Phase 2.
- ANTHROPIC_API_KEY not wired from `.env` by default — `src/.env` not created by compose. Copy `.env.example` → `.env` and set the key before running any LLM-dependent flow (BA/SA agents, Cohere rerank). S0–S2 are stub deterministic and need no key.
