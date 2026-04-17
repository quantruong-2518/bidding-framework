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
