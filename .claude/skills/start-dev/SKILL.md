---
name: start-dev
description: Start all dev services via Docker Compose and verify health
allowed-tools: Bash(docker*) Bash(curl*)
---

# Start Development Environment

1. Start infrastructure:
```bash
cd $CLAUDE_PROJECT_DIR/src && docker compose up -d
```

2. Wait for health checks:
```bash
cd $CLAUDE_PROJECT_DIR/src && docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

3. Verify each service:
- PostgreSQL: `docker compose exec postgres pg_isready`
- Qdrant: `curl -s http://localhost:6333/healthz`
- Redis: `docker compose exec redis redis-cli ping`
- Temporal: `curl -s http://localhost:7233/health`

4. If unhealthy, show logs: `docker compose logs <service> --tail 50`

5. Report status to user.
