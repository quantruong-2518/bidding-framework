---
doc_type: technology
domain: orchestration
tags: [workflow, durable-execution, saga]
---
# Temporal.io

## Capability Summary
Durable execution engine. We use it anywhere a business process spans hours or days, involves human approvals, or must survive worker restarts. Workflows are code; state is persisted by the engine.

## Where we have delivered
- [[vesta-onboarding]] — onboarding-as-workflow (document capture -> OCR -> AML -> core account open).
- [[medix-emr-2024]] — per-patient data migration with compensating saga semantics.
- [[telora-5g-bss]] — cross-domain provisioning orchestration across network functions.

## Patterns we use
- One workflow per long-running business entity (bid, onboarding case, patient migration).
- Activities = side-effectful units; keep deterministic logic in workflow code.
- Signals for human approvals; queries for read-only status exposure to a UI.
- Pair with [[microservices]] — activities call services; workflow owns the lifecycle.
