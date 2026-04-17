---
doc_type: technology
domain: architecture
tags: [architecture, event-sourcing, cqrs]
---
# Event Sourcing

## Capability Summary
Persist the domain as an append-only log of facts; derive current state by folding the log. Pairs with CQRS for read-side projections. Powerful where auditability, replay, and temporal queries matter — expensive everywhere else.

## Where we have delivered
- [[acme-core-banking]] — posting events provided the reconciliation source of truth during parallel run.
- [[telora-5g-bss]] — subscriber lifecycle domain eliminated a class of billing disputes.

## When to pick it
- Strong audit requirements (banking, healthcare ledger, trading).
- Multiple read models deriving from the same facts (dashboards, fraud, reconciliation).
- When you explicitly need time-travel queries ("what did we think on day T?").

## When to avoid
- CRUD-heavy domains with no audit pressure — stick to classical persistence.
- Teams unfamiliar with eventual consistency — the projection lag will bite.

## Related
- Typically combined with [[microservices]] + [[temporal-io]] orchestration in our stack.
