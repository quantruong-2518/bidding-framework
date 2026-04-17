---
name: check-health
description: Quick health check of all running services and current bid workflows
allowed-tools: Bash(docker*) Bash(curl*)
---

# Health Check

## 1. Docker Services
```bash
cd $CLAUDE_PROJECT_DIR/src && docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

## 2. API Gateway
```bash
curl -s http://localhost:3000/health | head -20
```

## 3. AI Service
```bash
curl -s http://localhost:8001/health | head -20
```

## 4. Temporal Workflows
```bash
curl -s http://localhost:7233/health
```

## 5. Qdrant
```bash
curl -s http://localhost:6333/collections | head -20
```

Report a table: service name, status (UP/DOWN), port, notes.
