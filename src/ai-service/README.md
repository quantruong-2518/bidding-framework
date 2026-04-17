# AI Service

Python FastAPI host for Temporal workers, LangGraph agents, and the RAG pipeline.

## Quickstart

```bash
cp .env.example .env
poetry install
poetry run uvicorn main:app --reload --port 8001
# Healthcheck: curl http://localhost:8001/health
poetry run pytest
```

Run the full stack (postgres, qdrant, redis, temporal, keycloak, frontend, api-gateway):
`cd .. && docker compose up -d`.
