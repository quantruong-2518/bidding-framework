---
project_id: proj-vesta-042
client: VestaBank
domain: banking
year: 2024
doc_type: project
tags: [kyc, onboarding, digital, identity]
---
# VestaBank — Digital Onboarding

## Context
VestaBank's branch-only onboarding averaged 38 minutes and a 24% drop-off rate at the ID verification step. The target was a fully digital onboarding flow compliant with SBV KYC requirements that could issue an account number within 6 minutes for 90% of applicants.

## Approach
A single-page [[nextjs]] front-end drives a state-machine backend built on [[temporal-io]]. Each onboarding is a long-running workflow: document capture -> OCR -> liveness -> AML screening -> underwriting -> core-banking account creation. The core-banking integration reuses the adapter pattern from [[acme-core-banking]]. Human review happens only when signals disagree (e.g., OCR confidence low but liveness high); everything else is STP.

## Tech Stack
[[nextjs]] 14, Go [[microservices]], [[temporal-io]] for workflow state, Amazon Textract for OCR, FaceTec for liveness, LexisNexis Bridger for AML, in-house adapter to the Temenos Transact core (same pattern as AcmeCorp). All on [[kubernetes]] (EKS).

## Outcomes
Median time-to-account-open: 4 min 12 sec. Drop-off at ID step fell from 24% to 6%. STP rate: 81% of applications. Branch onboarding volume dropped 62% as customers self-served, freeing staff for advisory work.

## Lessons
Liveness false-reject rate was the single biggest CX risk — we tuned it three times in the first month post-launch. The Temporal workflow pattern generalizes beautifully to other STP flows; we extracted it into [[proposal-skeleton]].
