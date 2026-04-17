---
doc_type: technology
domain: architecture
tags: [architecture, microservices, ddd]
---
# Microservices

## Capability Summary
Service decomposition along bounded contexts, typically 8–40 services per engagement. Preferred runtime [[kubernetes]]. Preferred inter-service contract: async events (Kafka) for state propagation, synchronous REST/gRPC only for command paths that need an immediate reply.

## Where we have delivered
- [[acme-core-banking]] — 28 services wrapping Temenos L3 APIs.
- [[telora-5g-bss]] — Go + Java services across the charging / CRM split.
- [[medix-emr-2024]] — ingestion + FHIR facade layer.
- [[ironworks-mes]] — edge-deployed services on k3s per plant.

## Patterns we use
- Outbox pattern for atomic DB + event emission.
- Saga orchestration via [[temporal-io]] (prefer orchestration over choreography for auditability).
- Pair with [[event-sourcing]] when the domain is transactionally critical (banking, billing).

## Anti-patterns to flag
- "Microservices from day one" for teams smaller than ~20 engineers — see [[estimation-pitfalls]].
- Synchronous chains >3 services deep without a circuit breaker strategy.
