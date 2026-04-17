# AI Bidding Framework

Multi-agent bidding/proposal framework cho enterprise. Temporal.io durable workflows + LangGraph AI agents (Claude Sonnet 4 + Haiku) tạo WBS, HLD, estimation, complete proposals qua 11-state pipeline với human-in-the-loop gates.

> **Phase 1: COMPLETE (2026-04-17)** — S0 → S1 (human gate) → S2 chạy end-to-end với mock LLM scorer. BA LangGraph agent + RAG + Obsidian ingestion + Keycloak-protected API + realtime dashboard đều sẵn sàng. Xem `CURRENT_STATE.md`.

---

## Quick start (full stack, 1 command)

```bash
# 1. Clone + vào repo
git clone <repo-url> bid-framework
cd bid-framework

# 2. Cấu hình env
cp src/.env.example src/.env
# mở src/.env và điền ANTHROPIC_API_KEY (bắt buộc nếu muốn chạy LLM thật)

# 3. Start toàn bộ (9 services)
cd src
docker compose up -d --build

# 4. Chờ healthcheck (~60–90s cho cold start đầu tiên)
docker compose ps            # tất cả phải là "healthy"
# hoặc theo dõi log
docker compose logs -f temporal ai-service api-gateway
```

Khi tất cả `healthy`:

| Service | URL | Ghi chú |
|---|---|---|
| **Frontend** | <http://localhost:3001> | Next.js — login "Demo mode" để xem dashboard + DAG viewer |
| **API Gateway** | <http://localhost:3000/health> | NestJS REST + WebSocket `/ws` |
| **AI Service** | <http://localhost:8001/docs> | FastAPI Swagger — gọi trực tiếp `/workflows/bid/*` |
| **Temporal UI** | <http://localhost:8088> | xem workflow execution, signals, history |
| **Keycloak Admin** | <http://localhost:8080> | admin / admin — realm `bidding` chưa provision (Phase 1.x) |
| **Qdrant** | <http://localhost:6333/dashboard> | vector DB console |
| Postgres | `localhost:5432` | bidding / bidding / bidding_db |
| Redis | `localhost:6379` | |
| Temporal gRPC | `localhost:7233` | worker connect endpoint |

**Stop:**
```bash
docker compose down            # stop, giữ data
docker compose down -v         # stop + xóa volumes (sạch hoàn toàn)
```

---

## First-time smoke test (end-to-end)

Sau khi stack `healthy`:

```bash
# 1. Seed knowledge base (9 sample project docs → Qdrant)
docker compose exec ai-service poetry run python -m rag.seed

# 2. Ingest Obsidian KB vault (20 notes + [[links]])
docker compose exec ai-service poetry run python -m ingestion --vault /app/../kb-vault

# 3. Mở frontend, click "Demo mode"
open http://localhost:3001

# 4. (Optional) Chạy workflow trực tiếp qua ai-service (bypass NestJS auth)
curl -X POST http://localhost:8001/workflows/bid/start-from-card \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "AcmeCorp",
    "industry": "banking",
    "region": "APAC",
    "deadline": "2026-06-30T00:00:00Z",
    "scope_summary": "Core banking modernization",
    "technology_keywords": ["microservices","kubernetes"],
    "estimated_profile": "L",
    "requirements_raw": []
  }'
# → nhận workflow_id; mở http://localhost:8088 thấy workflow running, pause ở S1

# 5. Gửi signal approve để tiếp tục sang S2
curl -X POST http://localhost:8001/workflows/bid/<workflow_id>/triage-signal \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "reviewer": "demo-user", "notes": "approved for demo"}'
```

> **Auth via NestJS:** Keycloak realm `bidding` chưa được provision trong Phase 1. Frontend "Demo mode" token sẽ bị `JwtAuthGuard` reject khi gọi NestJS. Để test qua gateway, hoặc (a) paste JWT thật từ Keycloak đã cấu hình, hoặc (b) gọi trực tiếp ai-service ở port 8001 như ví dụ trên. Provision realm là task đầu Phase 1.x / 2.

---

## Prerequisites

- **Docker Engine 24+** & **Docker Compose v2** (`docker compose` không phải `docker-compose`)
- **~6 GB RAM** free cho stack đầy đủ (Temporal + Keycloak nặng nhất)
- **Ports free:** 3000, 3001, 5432, 6333, 6379, 7233, 8001, 8080, 8088, 9000

Cho per-service dev (không qua Docker):
- Python 3.12+ + Poetry 1.8+
- Node 20+ + npm 10+

---

## Development workflows

### Full stack via Docker (khuyến nghị khi onboarding / demo)
```bash
cd src
docker compose up -d            # all services
docker compose logs -f <svc>    # xem log một service
docker compose restart <svc>    # restart sau khi sửa file + rebuild
docker compose up -d --build <svc>   # rebuild + restart một service
```

### Per-service dev (fast iteration, hot reload)
Giữ Docker chạy các dependencies (postgres, qdrant, redis, temporal, keycloak) và chạy service cần code ngoài Docker:

```bash
# Chỉ start deps
cd src && docker compose up -d postgres qdrant redis temporal keycloak

# ai-service (Python)
cd src/ai-service
poetry install
poetry run uvicorn main:app --reload --port 8001     # FastAPI
poetry run python worker.py                          # Temporal worker (shell khác)

# api-gateway (NestJS)
cd src/api-gateway
npm install
npm run start:dev

# frontend (Next.js)
cd src/frontend
npm install
npm run dev                     # http://localhost:3000 (khi chạy ngoài Docker)
```

Env file cho per-service dev: copy `src/<service>/.env.example` → `src/<service>/.env` và đổi hostname từ container name (`postgres`, `qdrant`, …) thành `localhost`.

---

## Testing

```bash
# Python (ai-service)
cd src/ai-service
poetry run pytest                          # all
poetry run pytest tests/test_workflow.py   # one file
poetry run pytest -k "triage"              # by name

# NestJS (api-gateway)
cd src/api-gateway
npm test                                   # src/**/*.spec.ts
npm run test:e2e                           # test/*.spec.ts (bids + workflows)

# Frontend (Next.js)
cd src/frontend
npx vitest run                             # once
npx tsc --noEmit                           # type check
npm run lint
npm run build                              # production build
```

Hoặc custom skill `/run-tests` chạy tất cả (xem `.claude/skills/run-tests/`).

---

## Project structure

```
bid-framework/
  CLAUDE.md                           # rules + conventions (Claude Code reads this auto)
  CURRENT_STATE.md                    # progress + next action — read first each session
  README.md                           # (this file)
  .mcp.json                           # MCP servers (postgres, filesystem-kb, github)
  .claude/                            # skills, hooks, permissions
  docs/
    architecture/SYSTEM_ARCHITECTURE.md    # tech stack + diagrams + Phase 1 impl map
    states/STATE_MACHINE.md                # 11-state workflow + impl pointers
    phases/PHASE_{1,2,3}_PLAN.md           # task breakdown per phase
  src/
    CLAUDE.md                         # services-level guide (container ops + ports)
    docker-compose.yml                # 9-service local stack
    .env.example                      # aggregated env template
    ai-service/
      CLAUDE.md                       # Python service guide
      main.py, worker.py, pyproject.toml
      workflows/, activities/, agents/, tools/, rag/, ingestion/, config/, tests/
    api-gateway/
      CLAUDE.md                       # NestJS service guide
      src/{auth,bids,workflows,gateway,redis}/
      package.json, tsconfig.json
    frontend/
      CLAUDE.md                       # Next.js app guide
      app/, components/, lib/, __tests__/
      package.json, next.config.mjs
    kb-vault/
      CLAUDE.md                       # Obsidian vault conventions
      projects/, clients/, technologies/, templates/, lessons/
```

> Mỗi sub-repo có `CLAUDE.md` riêng — mở Claude Code với cwd trong bất kỳ service nào cũng có full context (local + root merged).

---

## Environment variables

Copy `src/.env.example` → `src/.env` và điền:

| Key | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (nếu chạy LLM thật) | `sk-ant-…` từ console.anthropic.com |
| `COHERE_API_KEY` | No | Bật reranker; không set → trim fallback |
| `VOYAGE_API_KEY` | No | Alternative embedding; default dùng fastembed offline |
| `CORS_ORIGIN` | No | Mặc định `*` (dev only); set `http://localhost:3001` cho chặt |

Per-service env examples: `src/{ai-service,api-gateway,frontend}/.env.example`.

---

## Troubleshooting

| Triệu chứng | Cách xử lý |
|---|---|
| Temporal stuck ở `starting` 60–90s | Bình thường cho cold start — `auto-setup` đang init schemas vào Postgres. Healthcheck start_period 45s, check `docker compose logs temporal`. |
| Keycloak `unhealthy` | Management port 9000 lên sau HTTP port ~30s. Chờ tối đa 60s. |
| Port conflict 3000/3001 | Frontend: host 3001 → container 3000. API gateway: host+container 3000. Sửa `src/docker-compose.yml` nếu trùng. |
| `docker compose config` error | Chạy command đó trước khi `up` để bắt lỗi YAML syntax. |
| ai-service không reconnect Temporal | Worker nên có retry. Nếu Temporal restart, restart ai-service: `docker compose restart ai-service`. |
| NestJS trả 401 với JWT | Keycloak realm chưa provision → JWKS endpoint không tồn tại. Gọi trực tiếp ai-service ở 8001, hoặc provision realm trước. |
| Qdrant trả empty search | Chưa seed. Chạy `docker compose exec ai-service poetry run python -m rag.seed`. |

---

## Documentation map

Đọc theo thứ tự tùy mục đích:

| Mục đích | File |
|---|---|
| Onboard nhanh (dev mới) | `README.md` (this) → `CURRENT_STATE.md` → `docs/phases/PHASE_1_PLAN.md` |
| Hiểu kiến trúc toàn cục | `docs/architecture/SYSTEM_ARCHITECTURE.md` |
| Hiểu workflow 11 states | `docs/states/STATE_MACHINE.md` |
| Làm việc trong 1 service cụ thể | `src/<service>/CLAUDE.md` |
| Quy ước code + slash commands | `CLAUDE.md` (root) |
| Phase 2 / 3 roadmap | `docs/phases/PHASE_{2,3}_PLAN.md` |

---

## License & contact

Internal FSOFT project. Contact: (pending).
