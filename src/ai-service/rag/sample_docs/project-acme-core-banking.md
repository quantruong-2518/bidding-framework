---
project_id: proj-acme-001
client: AcmeCorp
domain: banking
year: 2023
doc_type: case-study
---
# AcmeCorp — Core Banking Migration

## Context
AcmeCorp, a tier-2 retail bank with 4.2M customers, ran a 22-year-old IBM mainframe COBOL core. Batch overnight postings were missing SLA 3–5 times per month, and the mainframe vendor announced end-of-support for the installed CICS version within 24 months. We won the prime role on a 26-month migration to Temenos Transact on AWS.

## Approach
We ran a parallel-run strategy. Every posting was written to both the legacy core and Transact for 9 months, with a reconciliation service (Kafka + Flink) flagging deltas above ₫50 tolerance. Cutover was account-type by account-type: savings -> current -> term deposits -> loans, each wave gated on <0.01% reconciliation mismatch across 14 consecutive days. A dedicated squad owned regulatory reporting (SBV daily position) which we kept on the legacy system until the final wave to de-risk audit exposure.

## Tech Stack
Temenos Transact R23, AWS (EKS, Aurora PostgreSQL, MSK), Kafka Connect JDBC + custom CDC for mainframe tables via IBM InfoSphere CDC, Flink for recon, Camunda for cutover orchestration. 28 microservices wrapped the Transact L3 APIs for mobile & internet banking. Keycloak fronted staff auth; customer auth stayed with the existing PingIdentity tenant.

## Outcomes
Go-live hit M+26 on budget (+3.8% contingency used). Overnight batch window fell from 6.1h to 1.9h. First-year opex dropped ₫48B versus the mainframe run-rate, clearing the business case hurdle with 14 months to spare. Three-month post-live incident count was 62% lower than the comparable pre-migration window.

## Lessons
The reconciliation service was the single biggest risk reducer — retrospectively we'd have started it 3 months earlier than we did. Underestimated effort on regulatory report parity (SBV format is undocumented in places) by 40%. Kafka Connect JDBC mainframe offset tracking was fragile; next time we'd use a purpose-built mainframe CDC agent from day one.
