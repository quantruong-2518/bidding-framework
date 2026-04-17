# System Architecture — AI Bidding Framework

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│                   Next.js (App Router)                        │
│         shadcn/ui + ReactFlow (DAG visualization)            │
│              SSE (streaming) + Socket.io (realtime)           │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    API GATEWAY                                │
│                   NestJS (TypeScript)                         │
│         Auth (Keycloak) │ RBAC Guards │ WebSocket Gateway     │
│         Audit Logging   │ Request Validation                  │
└────────────────────────┬────────────────────────────────────┘
                         │ Redis Streams (async) / gRPC (sync)
┌────────────────────────▼────────────────────────────────────┐
│                  AI ORCHESTRATION LAYER                       │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Temporal.io (Durable Workflows)             │   │
│  │  - DAG state machine (11 states)                      │   │
│  │  - Human-in-the-loop gates (signals)                  │   │
│  │  - Parallel activity dispatch                         │   │
│  │  - Timeout & escalation                               │   │
│  │  - Full audit trail (Visibility API)                  │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│  ┌──────────────▼───────────────────────────────────────┐   │
│  │     LangGraph Agents (trong Temporal Activities)      │   │
│  │                                                       │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐  │   │
│  │  │BA Agent │ │SA Agent │ │Domain   │ │Estimation│  │   │
│  │  │         │ │         │ │Agent    │ │Agent     │  │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └──────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│                 Python FastAPI Workers                        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    DATA LAYER                                 │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │PostgreSQL│  │ Qdrant   │  │  Redis   │  │Unstructured│  │
│  │(main DB) │  │(vector)  │  │(cache +  │  │.io (doc   │  │
│  │+ pgvector│  │hybrid RAG│  │ streams) │  │ parsing)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Outer Orchestration | Temporal.io | Durable state machine, audit trail, human gates, parallel dispatch |
| Agent Orchestration | LangGraph | AI agent graphs trong moi Temporal activity |
| Primary LLM | Claude Sonnet 4 (reasoning) + Haiku (extraction) | Tiered model routing theo complexity |
| LLM Abstraction | LiteLLM | Provider fallback, unified API |
| Vector DB | Qdrant (primary) + pgvector (convenience) | Hybrid search + reranking |
| Relational DB | PostgreSQL | Main data, RLS for RBAC |
| API Gateway | NestJS (TypeScript) | Auth, RBAC, WebSocket, structured API |
| AI Services | Python FastAPI + Temporal workers | LangGraph execution, RAG pipeline |
| Message Queue | Redis Streams | NestJS <-> Python communication |
| Frontend | Next.js App Router + shadcn/ui + ReactFlow | SSR, realtime, DAG visualization |
| Knowledge Workspace | Obsidian (Git sync) | KB authoring + Bid workspace |
| Doc Parsing | Unstructured.io (self-hosted) | PDF/DOCX extraction |
| Doc Generation | python-docx + Jinja2 templates | Template-controlled proposal output |
| Auth | Keycloak (self-hosted) | Enterprise identity, SSO |
| Observability | Langfuse (self-hosted) | LLM tracing, cost tracking |
| Deployment (Phase 1) | Docker Compose on VPS | Migrate to K8s in Phase 3 |

## Communication Flow

```
Frontend (Next.js)
    │
    │ REST / GraphQL
    ▼
API Gateway (NestJS)
    │
    ├── Redis Streams (async) ──► Python AI Workers
    │                              │
    │                              ├── Temporal Workflows
    │                              │     └── LangGraph Agents
    │                              │           └── Claude API (LLM)
    │                              │           └── Qdrant (RAG)
    │                              │
    │                              └── Ingestion Service
    │                                    └── Obsidian Vault (Git)
    │                                    └── Unstructured.io (parse)
    │
    ├── WebSocket ◄──── Redis Pub/Sub ◄──── Python Workers
    │   (realtime updates to frontend)
    │
    └── Keycloak (auth)
```

## Obsidian Integration

### KB Vault (shared, curated by SMEs)
- SMEs write/curate knowledge trong Obsidian voi markdown + [[links]] + YAML frontmatter
- [[links]] tu nhien tao knowledge graph (client <-> project <-> technology <-> lessons)
- Git-synced -> version control + audit trail
- Ingestion service watch changes -> parse -> embed -> Qdrant

### Bid Workspace (per-bid folders)
- Moi bid co folder rieng: requirements, stream outputs, solution, WBS, commercial
- AI output viet vao vault duoi dang markdown -> nguoi edit truc tiep trong Obsidian
- [[links]] giua requirements <-> solution components = traceability
- Graph View = thay ngay requirement nao chua duoc cover

### Ingestion Pipeline
```
Obsidian Vaults (KB + Bid Workspaces)
      | Git sync / filesystem watch
      v
Ingestion Service (Python)
  - Parse markdown + frontmatter
  - Extract [[links]] -> knowledge graph edges
  - Chunk & embed -> Qdrant
      |
      v
Qdrant (hybrid: dense + sparse + metadata filters)
  + Knowledge Graph (from [[links]])
      |
      v
Reranker (Cohere Rerank) -> Top 5 -> LLM context
```

## LLM Strategy: Full Claude API + Optimization

| Task type | Model | Est. cost |
|---|---|---|
| Complex reasoning (architecture, planning) | Claude Sonnet 4 | $0.50-2.00/run |
| Document extraction/summarization | Claude Haiku | $0.05-0.20/doc |
| Classification/routing | Claude Haiku | $0.001-0.01/call |
| Full bid workflow (11 states) | Mixed | $1-3/run (after optimization) |

### Optimization layers:
1. **Tiered routing**: Haiku cho 70% tasks, Sonnet cho 30% complex tasks
2. **Prompt caching**: Cache system prompts + frequent KB chunks -> giam 90% input cost
3. **Batch API**: Non-realtime tasks (retrospective, KB ingestion) -> giam 50%
4. **Context management**: RAG top-5 thay vi stuff full document -> giam 70-80% tokens
5. **Budget cap**: Temporal track spend per bid, alert khi vuot threshold

Estimated: ~$50-150/thang cho 50 bids.

## Cost Summary (Phase 1)

```
LLM API (Claude, tiered routing)   ~$50-150/th
VPS (2-3 servers, Docker Compose)  ~$100-200/th
All other components (self-hosted)  ~$0
────────────────────────────────────────────
TOTAL Phase 1:                     ~$150-350/th
```

---

## Implementation Map (2026-04-17, Phase 2.2 delivered)

Each architectural component maps to concrete files and containers. For the per-task delivery manifest see `docs/phases/PHASE_1_PLAN.md` ("Phase 1 Delivered Summary") and `docs/phases/PHASE_2_PLAN.md` ("Task 2.1 DELIVERED", "Task 2.2 DELIVERED"). The Phase-2.2 deltas (real LangGraph agents for S3a/b/c, heuristic S4, stub-fallback gate, `StreamInput` unification) are reflected in the §AI Orchestration block below.

### Frontend — Next.js App Router (`src/frontend/`)
- App Router routes: `app/{login,(authed)/dashboard,(authed)/bids,(authed)/bids/new,(authed)/bids/[id]}`
- ReactFlow DAG: `components/workflow/workflow-graph.tsx` (S0..S11 incl. S3a/b/c parallel row); `lib/utils/state-palette.ts` is the single source-of-truth for state labels/colors
- Auth: zustand store `lib/auth/store.ts` + PKCE URL builder `lib/auth/keycloak-url.ts` (demo-mode + paste-JWT until realm provisioned)
- Data layer: TanStack Query hooks `lib/hooks/use-bids.ts`; typed REST wrappers `lib/api/{client,bids,types}.ts`
- Realtime: singleton `socket.io-client` `lib/ws/socket.ts` + per-bid subscription hook `lib/ws/use-bid-events.ts` (invalidates Query cache on `bid.event`)

### API Gateway — NestJS (`src/api-gateway/`)
- Auth: `src/auth/` — `JwtStrategy` (JWKS via `jwks-rsa`), `JwtAuthGuard` + `RolesGuard` registered as `APP_GUARD`, `@Public()` / `@Roles(...)` / `@CurrentUser()` decorators
- Bids: `src/bids/` — DTOs (`class-validator`) + in-memory `Map` repo (Phase 2 → Postgres)
- Workflow proxy: `src/workflows/` — `WorkflowsService` uses `@nestjs/axios` to talk to ai-service at `AI_SERVICE_URL`; trigger hits `/workflows/bid/start-from-card` (snake_case body)
- WebSocket: `src/gateway/events.gateway.ts` — socket.io `/ws`, JWT handshake via `auth.token` or `Authorization` header
- Redis: `src/redis/` — two `ioredis` clients (publisher + subscriber), `XADD` streams + `PUBLISH` fanout
- Health: `GET /health` (public)

### AI Orchestration — Temporal + LangGraph (`src/ai-service/`)
- Workflow: `workflows/bid_workflow.py` (`@workflow.defn`), deterministic (`workflow.now()`, no host clock / uuid4 in body)
- Human gate: `human_triage_decision` signal + 24h `wait_condition` timeout → terminal `S1_NO_BID`
- Query: `get_state` returns `BidState` (Pydantic)
- Activities (`activities/`): `intake.py` (S0), `triage.py` (S1, wraps `agents/triage_agent.py` stub scorer), `scoping.py` (S2), `ba_analysis.py` / `sa_analysis.py` / `domain_mining.py` (S3a/b/c — real LangGraph wrappers with per-activity stub-fallback gate), `convergence.py` (S4 — heuristic rules + weighted readiness), `solution_design.py` … `retrospective.py` (S5..S11 deterministic stubs)
- HTTP surface: `workflows/router.py` — `POST /workflows/bid/start` (raw RFP), `POST /start-from-card` (pre-built BidCard), `POST /{id}/triage-signal`, `GET /{id}`
- Worker: `worker.py` — task queue `bid-workflow-queue`, SIGTERM/SIGINT graceful shutdown; registers 14 activities (3 S3 real agents + 10 stubs + 1 heuristic convergence; Phase 2.1 stream stubs stay importable for fallback but are not registered)
- S3 LangGraph agents (`agents/{ba,sa,domain}_agent.py`): 4-node graphs (`retrieve → Haiku classify/extract/tag → Sonnet synth → Sonnet critique → loop cap 2`); prompt caching via `cache_control: ephemeral` in `tools/claude_client.py`; shared `StreamInput` DTO in `workflows/artifacts.py`
- S3 fallback gate: each wrapper checks `get_claude_settings().api_key`; absent → delegates to the matching `activities/stream_stubs.py::*_stub_activity`; present → runs the real agent
- S4 convergence (`activities/convergence.py`): three heuristic rules (`_detect_api_mismatch`, `_detect_compliance_gap`, `_detect_nfr_field_mismatch`) + readiness `0.40·ba + 0.35·sa + 0.25·domain`, gate 0.80; pure-function `build_convergence_report` for testability

### RAG — Qdrant hybrid (`src/ai-service/rag/` + `config/qdrant.py`)
- Embeddings: `fastembed` default (bge-small-en-v1.5 dense + BM25 sparse); optional Voyage/Cohere
- Collection: named vectors (`dense` cosine + `sparse`) via `AsyncQdrantClient`
- Indexer: heading-aware chunker, UUID5 stable point IDs (idempotent re-ingest)
- Retriever: server-side RRF fusion via `query_points` + `Prefetch`; Cohere `rerank-english-v3.0` when key present, else trim fallback
- Seed: 9 sample docs under `rag/sample_docs/`; runnable `python -m rag.seed`

### Knowledge base — Obsidian + ingestion (`src/kb-vault/` + `src/ai-service/ingestion/`)
- Vault: 20 notes across `projects/`, `clients/`, `technologies/`, `templates/`, `lessons/` (81 `[[wiki-links]]`, 5 doc_types)
- Parser: `ingestion/vault_parser.py` (frontmatter + headings + links + sha256 hash)
- Watcher: `ingestion/watcher.py` (lazy `watchdog`, polling fallback, 500ms debounce)
- Service: `ingestion/ingestion_service.py` (hash-cache short-circuit, calls `rag.indexer.index_markdown_file`)
- Graph: `ingestion/graph_store.py` (in-memory `KnowledgeGraph` → JSON snapshot; swap-point for Neo4j/Kuzu in Phase 2)
- CLI: `python -m ingestion [--vault X] [--watch]` (honours `KB_VAULT_PATH`)

### Data layer (Phase 1 containers)
- `postgres:16-alpine` — Temporal persistence + (future) bid persistence
- `qdrant/qdrant:v1.12.4` — named-vector hybrid store
- `redis:7-alpine` — streams + pub/sub
- `temporalio/auto-setup:1.24.2` + `temporalio/ui:2.27.2`
- `quay.io/keycloak/keycloak:24.0` (start-dev, realm bootstrap deferred)

### Cross-service contracts
| From → To | Contract |
|---|---|
| Frontend → API Gateway | REST + `Authorization: Bearer <keycloak-token>`; camelCase DTOs |
| Frontend → API Gateway | socket.io `/ws` with `{auth:{token}}`; events `bid.event` (room `bid:{id}`) + `bid.broadcast` |
| API Gateway → AI Service | HTTP to `AI_SERVICE_URL` (default `http://ai-service:8001`); snake_case payloads |
| AI Service → Temporal | Task queue `bid-workflow-queue`, workflow id `bid-<uuid4>` |
| AI Service → Qdrant | collection `bid_knowledge` with named vectors `dense` + `sparse` |
| Ingestion → RAG | calls `rag.indexer.index_markdown_file` with frontmatter → metadata |

### Observability + operations (Phase 1 baseline)
- Python: stdlib `logging` per module; Temporal activity/workflow loggers
- NestJS: `Logger` injected per service/controller — no `console.*`
- Frontend: no telemetry yet (Phase 3.5 wires Langfuse + frontend events)
- Healthchecks: 9/9 services; dependency graph enforces `condition: service_healthy`
