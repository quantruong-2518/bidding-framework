# src/ — Services

Monorepo services orchestrated by `docker-compose.yml`.

## Layout

| Path | Role |
|------|------|
| `ai-service/` | Python 3.12 FastAPI + Temporal workers + LangGraph agents |
| `api-gateway/` | NestJS 10 — auth (Keycloak), RBAC, WebSocket, REST |
| `frontend/` | Next.js 14 App Router dashboard |
| `kb-vault/` | Obsidian knowledge base vault (Git-synced) |
| `docker-compose.yml` | Local dev stack (9 services) |

## Quickstart

```bash
cp .env.example .env           # fill in ANTHROPIC_API_KEY
docker compose up -d
docker compose ps              # confirm all services healthy
```

Exposed ports:

| Service       | URL                          |
|---------------|------------------------------|
| Frontend      | http://localhost:3001        |
| API Gateway   | http://localhost:3000/health |
| AI Service    | http://localhost:8001/health |
| Temporal UI   | http://localhost:8088        |
| Keycloak      | http://localhost:8080 (admin/admin) |
| Qdrant        | http://localhost:6333        |
| Postgres      | localhost:5432 (bidding/bidding) |
| Redis         | localhost:6379               |
| Temporal gRPC | localhost:7233               |

## Troubleshooting

- **Temporal stays `starting` for 30–60s** — `auto-setup` has to initialize
  Postgres schemas before accepting connections. The healthcheck waits up to
  ~5 min. If it exceeds that, check `docker logs bid-temporal` for schema
  errors and restart after Postgres is fully healthy.
- **Keycloak healthcheck fails immediately** — the management port (9000)
  comes up ~30s after the HTTP port. `start_period: 60s` covers most cases.
- **Qdrant healthcheck** uses a raw TCP probe via `bash /dev/tcp`. The image
  ships without `curl`.
- **Port 3000 conflict** — frontend listens on host `3001` mapped to internal
  `3000`; API gateway owns host `3000`. Adjust `ports:` if another dev server
  holds them.

## Per-service dev (without Docker)

```bash
# ai-service
cd ai-service && poetry install && poetry run uvicorn main:app --reload --port 8001

# api-gateway
cd api-gateway && npm install && npm run start:dev

# frontend
cd frontend && npm install && npm run dev
```
