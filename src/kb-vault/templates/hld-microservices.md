---
doc_type: template
domain: architecture
tags: [hld, template, microservices]
---
# HLD Template — Microservices on Kubernetes

## Purpose
Default HLD skeleton for any engagement picking [[microservices]] + [[kubernetes]]. Replace italics with client-specific content.

## 1. Context & Drivers
*What business problem. What constraints (regulatory, timeline, budget). What non-functionals (RPO/RTO, latency SLOs).*

## 2. Logical Architecture
- Bounded contexts and their service boundaries
- Inter-service contracts (sync vs async per boundary)
- Cross-cutting: AuthN/Z, observability, config, secrets

## 3. Physical Architecture
- [[kubernetes]] topology (clusters, namespaces, node pools)
- Data plane: Postgres / Kafka / Redis / Qdrant as needed
- Network: ingress, service mesh (only if you can justify it)

## 4. Data Architecture
- Per-service DB ownership
- Outbox + CDC if you need downstream projections
- Consider [[event-sourcing]] for audit-heavy domains

## 5. Cross-cutting
- Orchestration via [[temporal-io]] for long-running flows
- Observability: OpenTelemetry -> Tempo/Loki/Mimir or vendor equivalent
- Secrets via External Secrets Operator + cloud KMS

## 6. Risks
- See [[integration-risks]] for recurring items to pre-populate.
- Sizing pitfalls live in [[estimation-pitfalls]].

## 7. Migration / Rollout
*Strangler-fig pattern preferred. Reference [[nova-commerce-platform]] for an edge-routed example.*
