---
project_id: tmpl-wbs-banking-001
client: internal
domain: banking
year: 2024
doc_type: template
---
# WBS Template — Core Banking Migration

## 1. Mobilization & Discovery
- 1.1 Program setup, governance, RACI
- 1.2 Current-state architecture assessment (legacy core, peripheral systems, integrations)
- 1.3 Data landscape discovery (entities, volumes, data quality profile)
- 1.4 Regulatory & compliance baseline (central bank reporting, AML, data residency)
- 1.5 Vendor selection / target platform confirmation

## 2. Target Architecture & Design
- 2.1 Target core banking configuration (product catalog, GL chart, workflows)
- 2.2 Integration architecture (ESB/event bus, channel adapters, downstream consumers)
- 2.3 Non-functional architecture (HA/DR, security, performance budgets)
- 2.4 Data migration architecture (staging, transformation, reconciliation)
- 2.5 Cutover architecture (parallel-run vs big-bang, rollback design)

## 3. Build
- 3.1 Core platform configuration & parameterization
- 3.2 Channel adapter build (mobile, internet banking, ATM, branch teller, call center)
- 3.3 Regulatory reporting build
- 3.4 Data migration pipeline build (ETL + reconciliation jobs)
- 3.5 Non-functional build (monitoring, logging, backup, DR runbooks)

## 4. Test
- 4.1 Unit + component test
- 4.2 Integration test (channel -> core -> GL -> reporting)
- 4.3 Performance test (peak-hour + EOD batch window)
- 4.4 User acceptance test (business lines: retail, SME, corporate)
- 4.5 Disaster recovery drill (full failover + failback)
- 4.6 Regulatory test (reporting parity with legacy)

## 5. Data Migration & Reconciliation
- 5.1 Mock migration runs (minimum 3 full dress rehearsals)
- 5.2 Reconciliation design + tolerance sign-off with Finance/Risk
- 5.3 Parallel-run or cutover weekend execution
- 5.4 Post-cutover reconciliation & sign-off

## 6. Cutover & Hypercare
- 6.1 Cutover rehearsal (≥2 full runs)
- 6.2 Cutover execution
- 6.3 Hypercare (typically 60–90 days)
- 6.4 Knowledge transfer + run-book handover to operations

## 7. Program Management
- 7.1 Steering committee cadence
- 7.2 Risk & issue management
- 7.3 Regulator liaison
- 7.4 Change management & training
