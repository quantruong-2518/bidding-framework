---
project_id: proj-medix-007
client: MedixHealth
domain: healthcare
year: 2023
doc_type: case-study
---
# MedixHealth — EMR Integration Hub

## Context
MedixHealth, a 6-hospital regional group, ran three different EMRs (Epic at the flagship, Cerner at two acquisitions, a homegrown system at the smaller facilities) with no unified patient record. Clinicians averaged 11 minutes per cross-facility referral just to reconcile histories. The brief was to build an integration hub so any attending physician could see a merged longitudinal record within 3 seconds.

## Approach
We stood up a FHIR R4 integration layer. Each source EMR got a dedicated adapter: Epic via their standard FHIR API, Cerner via HL7 v2 bridged to FHIR with Mirth Connect, homegrown via nightly JDBC -> HL7 -> FHIR pipeline. A master patient index (Rhapsody EMPI) resolved identity across systems using a probabilistic match (Fellegi-Sunter) with clinician-in-the-loop review for 0.5 < score < 0.85. The merged record was served from a FHIR server (HAPI FHIR on PostgreSQL) with a caching layer (Redis, 90s TTL) fronting read-heavy encounters.

## Tech Stack
HAPI FHIR, PostgreSQL 15, Redis, Mirth Connect, Rhapsody EMPI, Keycloak with SMART-on-FHIR scopes, AWS GovCloud (HIPAA BAA), Kubernetes on EKS. Clinician UI was a Next.js app embedded as a SMART launch inside each native EMR.

## Outcomes
Cross-facility referral reconciliation time dropped from 11 minutes to 48 seconds median. 94% of merged records returned under the 3-second SLA. Zero PHI incidents in the first year post-launch. HIPAA audit (first external) passed with 2 low-severity findings, both documentation-related.

## Lessons
EMPI tuning took 4x longer than estimated — match thresholds needed per-facility calibration because data quality varied massively. Mirth Connect HL7 v2 handling is fine day-one but operationally heavy; on the next engagement we'd go Rhapsody end-to-end. SMART launch UX inside Cerner has quirks we didn't design around early enough.
