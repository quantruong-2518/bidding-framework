# AI Bidding Framework

## Project Overview
AI-powered bidding/proposal framework for enterprise. Multi-agent system that orchestrates parallel knowledge streams to generate WBS, HLD, estimation, and complete proposals.

## Quick Start for EVERY New Conversation
1. Read `CURRENT_STATE.md` — biết đang ở đâu, việc tiếp theo là gì
2. Read phase plan tương ứng trong `docs/phases/PHASE_X_PLAN.md`
3. Nếu cần hiểu architecture: `docs/architecture/SYSTEM_ARCHITECTURE.md`
4. Nếu cần hiểu workflow: `docs/states/STATE_MACHINE.md`

## Project Structure
```
bid-framework/
  CLAUDE.md                    # File này — đọc mỗi conversation
  CURRENT_STATE.md             # Progress tracking + next action
  docs/
    architecture/
      SYSTEM_ARCHITECTURE.md   # Tech stack, diagrams, cost
    states/
      STATE_MACHINE.md         # 11-state workflow chi tiết
    phases/
      PHASE_1_PLAN.md          # Tasks + file structure + done criteria
      PHASE_2_PLAN.md
      PHASE_3_PLAN.md
  src/
    ai-service/                # Python FastAPI + Temporal workers + LangGraph agents
    api-gateway/               # NestJS — auth, RBAC, WebSocket, REST API
    frontend/                  # Next.js App Router — dashboard, workflow viewer
    kb-vault/                  # Obsidian vault — knowledge base + bid workspaces
    docker-compose.yml
```

## Tech Stack
- **Orchestration:** Temporal.io (durable workflows) + LangGraph (AI agents)
- **LLM:** Claude Sonnet 4 (reasoning) + Haiku (extraction), via LiteLLM
- **Backend:** NestJS (API gateway, TypeScript) + Python FastAPI (AI workers)
- **Frontend:** Next.js 14 App Router + shadcn/ui + ReactFlow
- **Data:** PostgreSQL 16 + Qdrant + Redis 7
- **Knowledge:** Obsidian vault (Git sync) → ingestion → Qdrant
- **Auth:** Keycloak
- **Observability:** Langfuse (self-hosted)
- **Infra (Phase 1):** Docker Compose

## Commands
```bash
# Start all services
cd src && docker compose up -d

# Python AI service (dev)
cd src/ai-service && poetry run uvicorn main:app --reload --port 8001

# NestJS API gateway (dev)
cd src/api-gateway && npm run start:dev

# Next.js frontend (dev)
cd src/frontend && npm run dev

# Run Python tests
cd src/ai-service && poetry run pytest

# Run NestJS tests
cd src/api-gateway && npm run test

# Run frontend tests
cd src/frontend && npm run test
```

## Coding Conventions

### Python (ai-service)
- Package manager: **Poetry**
- Python 3.12+
- Type hints everywhere
- Async by default (FastAPI + async Temporal activities)
- Pydantic models for all data structures
- File naming: snake_case
- Tests: pytest, in `tests/` mirror of `src/`

### TypeScript — NestJS (api-gateway)
- Package manager: **npm**
- NestJS conventions: modules, controllers, services, guards
- DTOs with class-validator
- File naming: kebab-case (NestJS standard)
- Tests: Jest, co-located `.spec.ts`

### TypeScript — Next.js (frontend)
- Package manager: **npm**
- App Router (not Pages)
- Server Components by default, `"use client"` only when needed
- shadcn/ui components in `components/ui/`
- File naming: kebab-case for routes, PascalCase for components
- State: Zustand for client state, TanStack Query for server state
- Tests: Vitest + Testing Library

## Rules
- ALWAYS update `CURRENT_STATE.md` after completing a task (change status + add notes)
- ALWAYS read `CURRENT_STATE.md` at start of conversation
- Follow implementation order in phase plan — don't skip ahead
- Each Temporal activity wraps a LangGraph agent
- LLM calls: Haiku for extraction/classification, Sonnet for reasoning
- All AI output is advisory — human approves at gates
- Commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:` prefix
- No secrets in code — use environment variables
- Docker Compose for local dev, all services must have health checks

## Custom Skills (slash commands)
- `/start-dev` — Start Docker Compose + verify all services healthy
- `/run-tests` — Run all test suites (Python + NestJS + Next.js)
- `/check-health` — Quick health check of all running services
- `/new-agent <name>` — Scaffold a new LangGraph agent with Temporal activity
- `/new-state <S# name>` — Add a new state to Temporal bid workflow

## Built-in Skills to Use
- `/commit` — Commit with conventional commit message
- `/review` — Code review before merge
- `/security-review` — Security audit on changed files
- `/simplify` — Review changed code for quality and efficiency
- `/batch` — Parallelize large refactors across files

## MCP Servers (configured in .mcp.json)
- **postgres** — Query bid data, workflow state, audit logs
- **filesystem-kb** — Read/write Obsidian KB vault
- **github** — Issues, PRs (set GITHUB_PERSONAL_ACCESS_TOKEN)

## Hooks (auto-triggered)
- **PostToolUse (Write|Edit)** — Auto-format Python (black+ruff) and TS (prettier+eslint)

## Key Docs
- `CURRENT_STATE.md` — Progress + next action (READ FIRST)
- `docs/architecture/SYSTEM_ARCHITECTURE.md` — Full architecture
- `docs/states/STATE_MACHINE.md` — 11-state workflow
- `docs/phases/PHASE_1_PLAN.md` — Phase 1 details with file paths and done criteria
- `docs/phases/PHASE_2_PLAN.md` — Phase 2 plan
- `docs/phases/PHASE_3_PLAN.md` — Phase 3 plan
