---
project_id: proj-telora-022
client: TeloraTelecom
domain: telco
year: 2024
doc_type: project
tags: [bss, 5g, billing, charging, tm-forum]
---
# TeloraTelecom — 5G BSS Stack

## Context
TeloraTelecom needed a 5G-capable BSS (CRM + Billing + Charging) to launch standalone 5G to 8.4M subscribers. Legacy Amdocs stack couldn't handle slice-based charging or real-time policy on the timelines demanded by the regulator's 5G rollout covenant.

## Approach
Greenfield BSS on [[microservices]] with TM Forum Open APIs as the integration contract. The charging plane runs in-memory on Redis + a custom rules engine, fed by the NEF via event streams. [[event-sourcing]] underpinned the subscriber lifecycle domain — every state change is a replayable event, which eliminated an entire class of billing reconciliation disputes. Orchestration of provisioning across network functions ran on [[temporal-io]].

## Tech Stack
Go and Java [[microservices]], Kafka, Redis, PostgreSQL + ScyllaDB (subscriber state), [[kubernetes]] (self-managed on OpenStack), TM Forum Open APIs, ONAP integration for network orchestration, Prometheus + Grafana + Loki for observability.

## Outcomes
5G commercial launch hit the regulator deadline with 11 days of slack. Real-time charging latency p99 < 40ms. Billing dispute volume dropped 71% in the first 6 months post-cutover versus the legacy baseline.

## Lessons
TM Forum conformance testing is more expensive than any vendor admits — budget 1.5x whatever you estimate. The in-memory charging tier was the right call but the replay/restore story took two rewrites to get right.
