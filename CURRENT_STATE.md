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
- `cd src && docker compose up --build -d` → 9 services healthy (~60–90s cold start)
- Frontend at `http://localhost:3001` → Demo-mode login renders dashboard + ReactFlow DAG
- Temporal UI at `http://localhost:8088`
- ai-service direct API at `http://localhost:8001/docs` (Swagger)
- Keycloak admin at `http://localhost:8080` (admin/admin) — realm `bidding` not yet provisioned (Phase 1.x), so authenticated flows need a pasted JWT or realm import

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
- Postgres persistence for bids uses an in-memory Map in `bids.service.ts` — swap for TypeORM/Prisma in Phase 2
- CORS defaults to `*` when `CORS_ORIGIN` unset — tighten before any shared-environment deploy
