# CURRENT STATE — AI Bidding Framework

> File này dùng để track tiến độ. Mỗi conversation mới đọc file này trước.
> Cập nhật mỗi khi hoàn thành 1 task.

## Last Updated: 2026-04-17

## Overall Status: PLANNING COMPLETE

## >>> NEXT ACTION <<<
**Task 1.1: Setup project structure + Docker Compose**
- Init monorepo: Poetry (Python), npm (NestJS + Next.js)
- Docker Compose: PostgreSQL, Qdrant, Redis, Temporal, Keycloak
- See `docs/phases/PHASE_1_PLAN.md` Task 1.1 for details
- Done when: `docker compose up` starts all services, health checks pass

---

## Phase 1: Core Foundation (Weeks 1-4)

| # | Task | Status | Notes |
|---|---|---|---|
| 1.1 | Setup project structure + Docker Compose | NOT STARTED | |
| 1.2 | Temporal workflow: S0 (Intake) + S1 (Triage) + S2 (Scoping) | NOT STARTED | 3 states đầu tiên |
| 1.3 | 1 LangGraph agent (BA Agent) as PoC | NOT STARTED | Chạy trong Temporal activity |
| 1.4 | Basic RAG: Qdrant + embedding pipeline | NOT STARTED | |
| 1.5 | Obsidian KB vault structure + ingestion service | NOT STARTED | Parse markdown → Qdrant |
| 1.6 | NestJS API gateway + Keycloak auth | NOT STARTED | |
| 1.7 | Minimal Next.js frontend (bid dashboard) | NOT STARTED | |

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
