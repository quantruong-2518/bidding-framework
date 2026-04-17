# Phase 1: Core Foundation (Weeks 1-4)

> **Status: COMPLETE (2026-04-17)**. All 7 tasks delivered, `docker compose config` clean, per-service test suites green. See section "Phase 1 Delivered Summary" below for the file map.

## Goal
Xay dung PoC end-to-end: upload RFP -> parse -> triage -> scoping.
Chung minh Temporal + LangGraph + RAG hoat dong cung nhau.

---

## Task 1.1: Project Setup + Docker Compose

**What:**
- Init monorepo structure
- Docker Compose cho: PostgreSQL, Qdrant, Redis, Temporal, Keycloak
- Python FastAPI service skeleton
- NestJS API gateway skeleton
- Next.js frontend skeleton

**Docker Compose services:**
```yaml
services:
  postgres:       # Main DB + Temporal persistence
  qdrant:         # Vector DB for RAG
  redis:          # Cache + message streams
  temporal:       # Workflow orchestration
  temporal-ui:    # Temporal web UI (debug)
  keycloak:       # Auth
  api-gateway:    # NestJS
  ai-service:     # Python FastAPI + Temporal workers
  frontend:       # Next.js
```

**Done when:** `docker compose up` starts all services, health checks pass.

**DELIVERED:**
- `src/docker-compose.yml` — 9 services, `docker compose config` validates clean
- Healthchecks: postgres/redis idiomatic; qdrant+keycloak+temporal via `/dev/tcp`; keycloak runs `start-dev --health-enabled=true` on mgmt port 9000
- Temporal `auto-setup:1.24.2` with `DB=postgres12`, `start_period: 45s`
- Dep `condition: service_healthy` graph: postgres→temporal, {postgres,qdrant,redis,temporal}→ai-service, {postgres,redis,keycloak}→api-gateway, api-gateway→frontend
- Frontend port-mapped to host `3001` to avoid collision with api-gateway `3000`
- Python manifests: `src/ai-service/pyproject.toml` (Poetry) + `Dockerfile` (python:3.12-slim)
- Node manifests: `src/api-gateway/package.json` + multi-stage `Dockerfile` (node:20-alpine), same for `src/frontend/`
- `.env.example` files per service + root `src/.env.example`

---

## Task 1.2: Temporal Workflow — S0, S1, S2

**What:**
- Define Temporal workflow for first 3 states
- Each state = 1 Temporal activity
- S0 (Intake): accept RFP metadata, create Bid Card
- S1 (Triage): score bid, recommend bid/no-bid, wait for human signal
- S2 (Scoping): decompose requirements, assign to streams

**Key files:**
```
src/
  ai-service/
    workflows/
      bid_workflow.py          # Main Temporal workflow
    activities/
      intake.py                # S0 activity
      triage.py                # S1 activity
      scoping.py               # S2 activity
    agents/
      triage_agent.py          # LangGraph agent for scoring
```

**Done when:** Can trigger workflow via API, see it progress through S0->S1, pause at S1 for human approval signal, continue to S2.

**DELIVERED:**
- `workflows/bid_workflow.py` — `BidWorkflow` class with `@workflow.defn`, deterministic (uses `workflow.now()`, no `datetime.utcnow/uuid4` in body)
- `workflow.signal` = `human_triage_decision`; `workflow.query` = `get_state`; 24h gate timeout → terminal `S1_NO_BID`
- Activities: `activities/{intake,triage,scoping}.py` — each `@activity.defn`, single-arg Pydantic in/out, retry policy 3× backoff
- `workflows/models.py` — `BidCard`, `TriageDecision`, `HumanTriageSignal`, `RequirementAtom`, `ScopingResult`, `BidState`, `IntakeInput`, `BidWorkflowInput` (accepts `intake` OR `prebuilt_card`)
- `workflows/router.py` — `POST /workflows/bid/start` (from RFP text), `POST /workflows/bid/start-from-card` (from UI-entered BidCard — used by NestJS), `POST /{wfId}/triage-signal`, `GET /{wfId}`
- `worker.py` — SIGTERM/SIGINT graceful shutdown, task queue `bid-workflow-queue`
- `agents/triage_agent.py` — stub deterministic scoring (swap-point for real LLM in Phase 2)
- Tests: `tests/test_activities.py` (6) + `tests/test_workflow.py` (4 via `WorkflowEnvironment.start_time_skipping()` including 24h gate)

---

## Task 1.3: LangGraph BA Agent PoC

**What:**
- 1 LangGraph agent that acts as Business Analyst
- Takes requirements from S2 output
- Queries Qdrant KB for similar projects
- Generates Business Requirements Analysis draft
- Runs as a Temporal activity

**Key files:**
```
src/
  ai-service/
    agents/
      ba_agent.py              # LangGraph graph definition
    tools/
      kb_search.py             # Qdrant search tool for agent
      claude_client.py         # Claude API wrapper with caching
```

**Done when:** Agent can receive requirements, query KB, generate analysis draft, return structured output.

**DELIVERED:**
- `agents/ba_agent.py` — LangGraph `StateGraph` compiled once via `@lru_cache`; 4 nodes:
  1. `retrieve_similar` (RAG, `{client} {industry} + top atoms`)
  2. `extract_requirements` (Haiku `claude-haiku-4-5-20251001`, temp 0.0) — normalise atoms
  3. `synthesize_draft` (Sonnet `claude-sonnet-4-6`, temp 0.2, 4096 tokens) — JSON `BusinessRequirementsDraft`
  4. `self_critique` (Sonnet, temp 0.0) — coverage + confidence
  - Conditional loop: re-synthesise once if `confidence < 0.5 && iteration < 2`
- `agents/models.py` — `BARequirements`, `BusinessRequirementsDraft`, `FunctionalRequirement`, `RiskItem`, `SimilarProject`
- `agents/prompts/ba_agent.py` — 3 versioned system prompts (extract/synthesize/review)
- `tools/claude_client.py` — `AsyncAnthropic` wrapper, prompt caching via `cache_control: {"type":"ephemeral"}` on system block; captures `cache_read_input_tokens` + `cache_creation_input_tokens`
- `tools/kb_search.py` — degrades to `[]` on Qdrant failure
- `activities/ba_analysis.py` — `@activity.defn ba_analysis_activity`, `activity.heartbeat()` around graph
- NOTE: activity not yet registered in `worker.py` — wired in Phase 2.2 (parallel S3a/b/c)
- Tests: `tests/test_claude_client.py` (4, asserts cache_control + usage) + `tests/test_ba_agent.py` (3, mocked LLM+RAG, loop cap verified)

---

## Task 1.4: Basic RAG — Qdrant + Embedding Pipeline

**What:**
- Embedding service using Claude/OpenAI embeddings
- Qdrant collection with hybrid search (dense + sparse)
- Metadata filtering (project, client, domain, year)
- Simple reranking
- Seed with 5-10 sample project documents

**Key files:**
```
src/
  ai-service/
    rag/
      embeddings.py            # Embedding generation
      indexer.py               # Document indexing into Qdrant
      retriever.py             # Search + rerank pipeline
    config/
      qdrant_schema.py         # Collection schema
```

**Done when:** Can index a document, search by query, get relevant results with metadata.

**DELIVERED:**
- `rag/embeddings.py` — `FastEmbedDenseProvider` (bge-small-en-v1.5, 384d, default, offline) + `FastEmbedSparseProvider` (BM25); optional `VoyageDenseProvider`; `anyio.to_thread.run_sync` to offload sync ONNX
- `config/qdrant.py` — `QdrantSettings`, `AsyncQdrantClient`, `ensure_collection` with named vectors (`dense` cosine + `sparse`) + payload indexes
- `rag/indexer.py` — heading-aware `chunk_markdown`, UUID5 stable point IDs (`parent_doc_id::chunk_index`) for idempotent re-ingest, inline frontmatter parser
- `rag/retriever.py` — `hybrid_search` via `query_points` with `Prefetch` (dense + sparse) + server-side RRF fusion; `rerank` uses Cohere `rerank-english-v3.0` when `COHERE_API_KEY` set, else trim fallback
- `rag/sample_docs/` — 9 seed markdown files across 6 domains (banking, e-commerce, healthcare, saas, telco, manufacturing) + WBS/HLD templates
- `rag/seed.py` — runnable as `python -m rag.seed`
- Deps added to `pyproject.toml`: `fastembed ^0.3.0`, `anyio ^4.4.0`, `cohere ^5.10.0` (all tagged `# task 1.4`)
- Tests: `tests/test_rag.py` (7, all mocks — no live Qdrant required)

---

## Task 1.5: Obsidian KB Vault + Ingestion

**What:**
- Create sample Obsidian vault structure for KB
- Ingestion service: watch vault -> parse markdown -> extract frontmatter + [[links]] -> embed -> Qdrant
- Git hook or filesystem watcher for auto-sync

**Vault structure:**
```
kb-vault/
  projects/
    project-abc-banking.md     # With YAML frontmatter
    project-xyz-ecommerce.md
  technologies/
    microservices.md
    cloud-native.md
  templates/
    wbs-template-banking.md
    hld-template.md
```

**Key files:**
```
src/
  ai-service/
    ingestion/
      vault_parser.py          # Parse Obsidian markdown
      link_extractor.py        # Extract [[links]] -> graph edges
      watcher.py               # Filesystem/git watcher
```

**Done when:** Edit a note in Obsidian -> change detected -> parsed -> indexed in Qdrant -> searchable.

**DELIVERED:**
- `src/kb-vault/` seeded with 20 markdown notes across `projects/` (6), `clients/` (3), `technologies/` (5), `templates/` (3), `lessons/` (2) + `.obsidian/{app,workspace}.json`; 81 `[[wiki-links]]`; 5 `doc_type` categories
- `ingestion/vault_parser.py` — `ParsedNote` (path, frontmatter, links, headings, sha256 content_hash); handles inline + block-list YAML
- `ingestion/link_extractor.py` — `[[target|alias]]` + `[[folder/target]]` normalisation; `build_edges` produces `LinkEdge` list
- `ingestion/vault_scanner.py` — async `.md` generator; skips `.obsidian/`, `.git/`
- `ingestion/graph_store.py` — in-memory `KnowledgeGraph` (outgoing + incoming indexes), JSON snapshot with dangling-link stats (graph-DB swap-point for Phase 2)
- `ingestion/watcher.py` — lazy `import watchdog` with asyncio polling fallback; debounce 500ms
- `ingestion/ingestion_service.py` — `initial_index` + `on_file_change` with hash-cache short-circuit; calls `rag.indexer.index_markdown_file` with frontmatter → metadata
- `ingestion/__main__.py` — `python -m ingestion [--vault X] [--watch]`, respects `KB_VAULT_PATH`
- `config/ingestion.py` — `IngestionSettings` (env-prefix `KB_`)
- Deps added: `watchdog ^5.0.0` (optional; polling fallback)
- Tests: `tests/test_ingestion.py` (7, all `tmp_path`-based with stub indexer)

---

## Task 1.6: NestJS API Gateway + Auth

**What:**
- NestJS project with module structure
- Keycloak integration (JWT validation)
- RBAC guards (roles: admin, bid_manager, ba, sa, qc)
- REST endpoints for: bids CRUD, workflow trigger, workflow status
- WebSocket gateway for real-time updates
- Redis Streams producer (send messages to Python workers)

**Key files:**
```
src/
  api-gateway/
    src/
      auth/                    # Keycloak JWT guard
      bids/                    # Bids module (CRUD)
      workflows/               # Trigger & status endpoints
      gateway/                 # WebSocket gateway
      redis/                   # Redis Streams producer
```

**Done when:** Can login via Keycloak, create a bid via API, trigger workflow, receive status updates via WebSocket.

**DELIVERED:**
- `src/auth/` — `JwtStrategy` (JWKS via `jwks-rsa` against `{KEYCLOAK_ISSUER}/protocol/openid-connect/certs`, RS256, audience + issuer checked); `JwtAuthGuard` + `RolesGuard` registered as `APP_GUARD`; `@Public()`, `@Roles(...)`, `@CurrentUser()` decorators
- `src/bids/` — in-memory Map repo (swap-point tagged for Phase 2), DTOs with `class-validator`, CRUD with role gating (create/update: admin+bid_manager; delete: admin only)
- `src/workflows/` — proxy to ai-service: trigger hits `POST /workflows/bid/start-from-card` with snake_case `BidCard` body; signal → `/{wfId}/triage-signal`; status → `GET /{wfId}`; Axios error mapping (404/408/502)
- `src/gateway/events.gateway.ts` — socket.io `/ws`, JWT handshake via `auth.token` or `Authorization` header (same JWKS config); per-bid rooms; emits `bid.event` + `bid.broadcast`
- `src/redis/` — two ioredis clients (publisher + subscriber), `XADD` for streams + `PUBLISH` for WS broadcast fanout
- Deps added: `@nestjs/axios`, `axios`, `helmet`, `uuid`, `jsonwebtoken` + `@types/*`
- Tests: `test/bids.controller.spec.ts` + `test/workflows.controller.spec.ts` — 8/8 via `npm run test:e2e` (default `npm test` only picks `src/**` — see Known Gaps)
- Keycloak realm `bidding` **not yet provisioned** (blocks live auth; demo-mode token used by frontend)

---

## Task 1.7: Minimal Next.js Frontend

**What:**
- Next.js App Router project
- Auth flow (Keycloak login)
- Bid Dashboard: list bids, create new bid
- Workflow Viewer: show current state of a bid workflow (ReactFlow DAG)
- Real-time status updates via SSE/WebSocket

**Key files:**
```
src/
  frontend/
    app/
      page.tsx                 # Dashboard
      bids/
        page.tsx               # Bid list
        [id]/page.tsx          # Bid detail + workflow viewer
        new/page.tsx           # Create new bid
    components/
      WorkflowGraph.tsx        # ReactFlow DAG visualization
      BidCard.tsx
      StatusBadge.tsx
```

**Done when:** Can login, see bid list, create bid, see workflow progress in real-time DAG view.

**DELIVERED:**
- App Router routes: `/login`, `(authed)/dashboard`, `(authed)/bids`, `(authed)/bids/new`, `(authed)/bids/[id]`
- `components/workflow/workflow-graph.tsx` — ReactFlow DAG; S3a/b/c laid out horizontally at row 3; status palette (`done`/`active` animated/`pending`/`skipped`) covers all `WorkflowState` literals including `S1_NO_BID`, `S2_DONE`
- `components/bids/triage-review-panel.tsx` — approve/reject + optional bid-profile override, posts camelCase to NestJS
- `lib/api/client.ts` — fetcher attaches `Authorization: Bearer <token>` from zustand store
- `lib/ws/{socket,use-bid-events}.ts` — singleton socket.io client per token; hook subscribes/unsubscribes per bid room, invalidates TanStack Query cache on `bid.event`
- `lib/auth/store.ts` + `lib/auth/keycloak-url.ts` — zustand auth state; PKCE URL builder (demo-mode button + paste-JWT form used until realm provisioned)
- `lib/utils/state-palette.ts` — single source-of-truth label/color/description per WorkflowState
- Deps added: `react-hook-form ^7`, `@hookform/resolvers ^5`, `date-fns ^4`
- Tests: `__tests__/` 4 specs / 24 cases; `tsc --noEmit`, `next build`, `eslint` all clean

---

## Implementation Order

```
1.1 Project Setup         ──> FIRST (foundation)
1.4 Basic RAG             ──> can start parallel with 1.2
1.2 Temporal Workflow      ──> depends on 1.1
1.3 BA Agent PoC          ──> depends on 1.2 + 1.4
1.5 Obsidian Ingestion    ──> depends on 1.4
1.6 NestJS API            ──> can start parallel with 1.2
1.7 Next.js Frontend      ──> depends on 1.6
```

```
Week 1: 1.1 + 1.4 + 1.6 (parallel)
Week 2: 1.2 + 1.6 (continue)
Week 3: 1.3 + 1.5 + 1.7
Week 4: 1.7 (continue) + integration testing + polish
```

---

## Phase 1 Delivered Summary (2026-04-17)

> **Update (2026-04-17 PM):** A cold-start verification pass uncovered 7 defects (Docker healthchecks + missing `ai-worker` service + frontend build-arg inlining + fastembed/Python range + Temporal pydantic converter + BA agent degraded-mode loop). All fixed; see `CURRENT_STATE.md` → "Phase 1 Hardening Pass" for the full list + re-usable verification runbook. Phase 1 is now **verified end-to-end** on a fresh `docker compose up --build`, with all 32 ai-service + 8 api-gateway + 24 frontend tests green.


### Actual execution waves
- **Wave 1** (sequential) → Task 1.1 foundation + audit
- **Wave 2** (parallel) → Tasks 1.2 / 1.4 / 1.6 + integration audit (found 1 blocker: payload-schema mismatch between NestJS trigger and Python `/start` — fixed by adding `/start-from-card` endpoint that accepts a pre-built `BidCard`, so NestJS-entered structured bids skip S0)
- **Wave 3** (parallel) → Tasks 1.3 / 1.5 / 1.7 + final integration audit

### Test coverage snapshot
| Service | Suite | Count | Status |
|---|---|---|---|
| `ai-service` | `tests/test_activities.py` | 6 | green (syntax + model validated on host; runtime in Docker) |
| `ai-service` | `tests/test_workflow.py` | 4 | green via `WorkflowEnvironment.start_time_skipping()` (24h gate incl.) |
| `ai-service` | `tests/test_rag.py` | 7 | green on host (mocked Qdrant) |
| `ai-service` | `tests/test_ingestion.py` | 7 | green on host (tmp_path) |
| `ai-service` | `tests/test_ba_agent.py` | 3 | green on host (mocked LLM+RAG) |
| `ai-service` | `tests/test_claude_client.py` | 4 | green on host (AsyncMock) |
| `api-gateway` | `test/bids.controller.spec.ts` + `test/workflows.controller.spec.ts` | 8 | green via `npm run test:e2e` |
| `frontend` | `__tests__/*` | 24 | green (`npx vitest run`); `tsc --noEmit` + `npm run build` + lint all clean |

### Cross-service contracts locked in Phase 1
- `POST /bids/:id/workflow` (NestJS, JWT required) → `POST http://ai-service:8001/workflows/bid/start-from-card` with snake_case `BidCard` body (`bid_id, client_name, industry, region, deadline, scope_summary, technology_keywords, estimated_profile, requirements_raw`)
- `POST /bids/:id/workflow/triage-signal` (camelCase) → `POST /workflows/bid/{wfId}/triage-signal` (snake_case via proxy transform)
- `GET /bids/:id/workflow/status` → `GET /workflows/bid/{wfId}` (returns `BidState`)
- WebSocket: frontend subscribes on `/ws` namespace with `{auth:{token}}`; server emits `bid.event` (per-bid room) and `bid.broadcast` (fleet-wide)

### Known gaps carried into Phase 2
- Keycloak realm `bidding` not yet provisioned — `docker-compose.yml` runs `start-dev` without `--import-realm`. Live auth needs realm JSON + `bidding-api` + `bidding-web` clients.
- `ba_analysis_activity` implemented but **not yet registered** in `worker.py` — Phase 2.2 wires S3a/b/c in parallel.
- `bids.service.ts` stores bids in-memory Map — swap for Postgres (TypeORM/Prisma) in Phase 2.
- Api-gateway default `npm test` uses `rootDir=src` → run `npm run test:e2e` to execute the 8 controller specs under `test/`.
- CORS defaults to `*` when `CORS_ORIGIN` unset — tighten before any shared deploy.
