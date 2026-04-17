---
doc_type: template
domain: banking
tags: [wbs, template, migration]
---
# WBS Template — Banking Core Migration

## Purpose
Work-breakdown baseline for a core banking migration bid. Calibrated on [[acme-core-banking]] and cross-checked against [[vesta-onboarding]] for the digital channel line items. Always rescale for client size before use.

## Phase 0 — Mobilize (4–8 weeks)
- 0.1 Stakeholder map + steerco cadence
- 0.2 Regulatory scope (central bank, deposit insurance)
- 0.3 Environment standup ([[kubernetes]], observability, CI/CD)
- 0.4 Data classification + PII inventory

## Phase 1 — Foundation (8–12 weeks)
- 1.1 Integration platform ([[microservices]] chassis, Kafka, API gateway)
- 1.2 [[event-sourcing]] backbone for the ledger domain
- 1.3 Reconciliation service design — DO NOT defer, see [[estimation-pitfalls]]
- 1.4 Cutover runbook skeleton

## Phase 2 — Parallel Run (6–9 months)
- 2.1 Dual-write orchestration via [[temporal-io]]
- 2.2 Reconciliation daily ops (+ tolerance tuning)
- 2.3 Regulatory reporting parity
- 2.4 Branch / contact-center readiness

## Phase 3 — Wave Cutover (3–6 months)
- 3.1 Savings
- 3.2 Current
- 3.3 Term deposits
- 3.4 Loans
- 3.5 Legacy decommission

## Cross-cutting
- Audit + SOX controls (every phase)
- Training (start M-6 before first wave)
- See [[integration-risks]] for recurring risk items to pre-load into the register.
