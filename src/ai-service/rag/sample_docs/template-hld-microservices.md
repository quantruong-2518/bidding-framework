---
project_id: tmpl-hld-msa-001
client: internal
domain: saas
year: 2024
doc_type: template
---
# HLD Template — Cloud-Native Microservices Platform

## 1. Solution Overview
One-paragraph business context, scope boundary (what is in / out), key drivers (cost, time-to-market, compliance), and a labelled system context diagram showing external actors and upstream/downstream systems.

## 2. Logical Architecture
Service decomposition (bounded contexts), ownership map, inter-service communication style (sync REST / async event), and a data ownership matrix showing which service is the system-of-record for each entity. Include an event catalogue for published domain events.

## 3. Deployment Architecture
Kubernetes topology (namespaces, node pools), ingress and service-mesh choice, secrets management, per-environment (dev / staging / prod) sizing, regional or multi-region posture, and disaster-recovery RPO/RTO targets per service class.

## 4. Data Architecture
Per-service database selection with rationale, shared-nothing rules, read-replica and caching strategy, schema migration approach, analytics / lakehouse integration path, and data classification (PII, PCI, PHI as applicable) with the resulting control set.

## 5. Integration Architecture
External system inventory (auth, payments, CRM, email, etc.) with protocol, SLA, failure-mode handling, and rate-limit posture. Internal event backbone (Kafka / Pulsar / managed queue) topic naming, retention, and replay strategy.

## 6. Security Architecture
Identity (customer + staff), authorization model (roles/ABAC), secret management, encryption at rest + in transit, network segmentation, WAF + DDoS, vulnerability management, logging + audit, and the compliance frameworks in scope (SOC 2, ISO 27001, PCI, HIPAA, etc.).

## 7. Observability
Metrics (RED + USE), tracing (OpenTelemetry standard), logs (structured JSON), log retention & PII redaction rules, alerting policy (pager-worthy vs ticket-worthy), SLO catalogue, error budget policy.

## 8. CI/CD & Environments
Branching strategy, build pipeline, artifact registry, supply-chain security (SBOM, signed images), promotion flow across environments, database change management, and feature-flag posture.

## 9. Non-Functional Requirements
Tabulated NFRs per service: availability target, performance budget (p50/p95/p99), scalability headroom, recovery targets. Capacity model with load-growth assumptions.

## 10. Risks & Assumptions
Top risks with likelihood × impact, mitigation owner, and review cadence. Explicit list of assumptions that, if invalidated, would trigger an architectural re-plan.
