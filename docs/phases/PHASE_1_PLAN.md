# Phase 1: Core Foundation (Weeks 1-4)

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
