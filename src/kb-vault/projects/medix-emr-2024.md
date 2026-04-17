---
project_id: proj-medix-007
client: MedixHealth
domain: healthcare
year: 2024
doc_type: project
tags: [emr, hl7-fhir, hipaa, integration]
---
# MedixHealth — EMR Modernization

## Context
[[medix]] operates 14 hospitals and 62 clinics on a 2009-era Allscripts EMR with a tangle of HL7 v2 interfaces. The modernization mandate was a phased migration to a FHIR-native EMR with no loss of clinical history and strict HIPAA audit continuity.

## Approach
We stood up a FHIR facade over the legacy EMR first — read-only — to prove data extraction fidelity against 14 years of encounter history. Then a [[microservices]] ingestion layer running on [[kubernetes]] began dual-writing to the new Oracle Health platform. Ambulatory clinics cut over first, acute care followed once the medication reconciliation subsystem passed three full clinical sign-off cycles. [[temporal-io]] drove the per-patient data migration workflows with compensating saga semantics for partial failures.

## Tech Stack
Oracle Health (Cerner Millennium), HAPI FHIR server, Mirth Connect for legacy HL7 v2 bridging, [[kubernetes]] (EKS), PostgreSQL for audit + FHIR meta, Kafka for clinical event streaming, Okta for workforce SSO.

## Outcomes
All 62 clinics live at M+11. Average chart load time down from 7.2s to 1.4s. Zero HIPAA audit findings in the first two post-migration quarterly reviews. Clinical documentation time per encounter dropped 18%.

## Lessons
Medication reconciliation is where clinical safety risk concentrates — we committed 2x the testing budget we originally sized and it was still tight. See [[integration-risks]] for the HL7 v2 ambiguity patterns we hit repeatedly.
