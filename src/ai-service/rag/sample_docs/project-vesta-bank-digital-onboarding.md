---
project_id: proj-vesta-052
client: VestaBank
domain: banking
year: 2024
doc_type: case-study
---
# VestaBank — Digital Customer Onboarding

## Context
VestaBank, a mid-sized commercial bank, had a branch-based onboarding funnel averaging 42 minutes per new retail account and a 31% abandonment rate on the self-service web attempt. Regulatory requirements (local eKYC, AML screening, FATCA/CRS) had never been fully digitized. The program goal was a mobile-first onboarding that stayed fully compliant and achieved account activation in under 8 minutes for 80% of applicants.

## Approach
We built a React Native onboarding app backed by a Temporal-orchestrated workflow. Stages: ID capture (front/back + liveness), OCR + MRZ parse, face-match against the ID photo, sanctions/PEP screening (Dow Jones Risk & Compliance), internal dedup against the core, product selection, account creation in core, and card issuance. Each stage was a Temporal activity so a failure at PEP screening (e.g., vendor timeout) didn't lose the earlier identity capture. A human-review queue absorbed the 6–8% of cases that fell into manual review; the same workflow resumed post-review via a signal.

## Tech Stack
React Native, AWS Rekognition (face-match + liveness as fallback, primary was iProov), Dow Jones Risk & Compliance for sanctions, Onfido for doc verification, Temporal for the onboarding workflow, Kafka between the workflow and the core (Temenos Transact), Keycloak for the agent-review console.

## Outcomes
Median activation time: 5.4 minutes. 78% of applicants completed fully self-serve (within 1pp of the 80% target). Manual-review queue stabilized at 7.1% of applications. Branch walk-in for retail account opening dropped 44% in the first six months. External audit of the eKYC evidence trail passed first time.

## Lessons
Temporal was the right spine for the workflow — without it, partial-application recovery would have been a nightmare. iProov liveness quality was materially better than Rekognition for our population; starting with the cheaper fallback would have hurt conversion. Dedup rules against the core surfaced data-quality problems nobody had prioritized before.
