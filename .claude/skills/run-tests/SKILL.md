---
name: run-tests
description: Run all test suites across Python, NestJS, and Next.js
allowed-tools: Bash(poetry*) Bash(npm*) Bash(cd*)
---

# Run All Tests

Run tests for all services. Report results per service.

## Python AI Service
```bash
cd $CLAUDE_PROJECT_DIR/src/ai-service && poetry run pytest -v --tb=short
```

## NestJS API Gateway
```bash
cd $CLAUDE_PROJECT_DIR/src/api-gateway && npm test
```

## Next.js Frontend
```bash
cd $CLAUDE_PROJECT_DIR/src/frontend && npm test
```

## Summary
Report: total passed, failed, skipped per service. If any failures, show the failing test details.
