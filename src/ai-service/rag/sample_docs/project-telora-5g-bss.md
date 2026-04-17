---
project_id: proj-telora-033
client: TeloraMobile
domain: telco
year: 2022
doc_type: case-study
---
# TeloraMobile — 5G BSS Modernization

## Context
TeloraMobile was deploying a 5G standalone core and needed its 18-year-old legacy BSS (charging, billing, CRM) replaced in parallel. The legacy system couldn't model network slices, dynamic QoS-tier charging, or the IoT MVNO partner model required by the new wholesale strategy. Regulator-mandated number portability and roaming interconnect reconciliation had to continue without interruption across cutover.

## Approach
We deployed Matrixx Digital Commerce as the converged charging system, integrated it with the 5G Charging Function (CHF via Nchf) and a new SAP BRIM revenue management stack. Legacy postpaid ran in parallel for 11 months on a per-cohort migration — prepaid moved first (2.1M subscribers) in a weekend cutover behind a dual-dip strategy at the SMPP layer. Postpaid moved in 4 waves by billing cycle. Number portability and interconnect reconciliation stayed on legacy until the final postpaid wave closed.

## Tech Stack
Matrixx Digital Commerce, SAP BRIM (FI-CA, Convergent Invoicing), 5G Core CHF integration (Nchf SBI), Kafka for event streaming, OpenShift on bare metal for low-latency charging pods, Camunda for cutover orchestration, Splunk for the regulator-auditable event log.

## Outcomes
Entire 6.4M-subscriber base on the new BSS at M+14 (plan was M+15). First-call resolution on billing disputes up 23% due to converged real-time balance. Network-slice-based B2B plans (private networks for 3 enterprise customers) went live within 60 days of core 5G SA launch. Wholesale MVNO onboarding time dropped from 16 weeks to 5 weeks.

## Lessons
CHF integration test cycles were the critical path — the vendor's Nchf conformance harness was immature in 2022 and we built our own. Underestimated effort on SAP BRIM tax localization (each region has its own VAT rules). The dual-dip SMPP strategy for prepaid cutover worked flawlessly and is now our standard playbook.
