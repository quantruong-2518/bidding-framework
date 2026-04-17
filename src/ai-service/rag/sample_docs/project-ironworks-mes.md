---
project_id: proj-iron-044
client: IronworksManufacturing
domain: manufacturing
year: 2023
doc_type: case-study
---
# Ironworks — Smart Factory MES Rollout

## Context
Ironworks operates 9 precision-machining plants across three countries. Each plant ran a different MES (or none), OEE data was compiled manually in Excel weekly, and traceability on safety-critical automotive components relied on paper travelers. The brief was a common MES platform, real-time OEE to the shop floor, and IATF 16949–grade digital traceability — rolled across all 9 plants in 18 months.

## Approach
Single Opcenter Execution instance per region (APAC, EMEA, AMER) to keep the shop-floor-to-server latency under 80ms. Plants connected via a per-plant edge gateway (Kepware + a thin Rust aggregator) that normalized PLC tags from a mix of Siemens S7, Allen-Bradley, and Mitsubishi Q-series into a common Ignition tag schema. Digital traveler was a tablet-based flow replacing paper on the machining line, with signatures captured via plant badge (ISO 27001 AD-backed). Rollout followed a pilot-plant-per-region approach before scaling.

## Tech Stack
Siemens Opcenter Execution, Ignition SCADA, Kepware edge, Rust gateway on Linux industrial PCs, Kafka bridging edge -> cloud, Snowflake for cross-plant analytics, Power BI dashboards, MQTT (Sparkplug B) for shop-floor telemetry, Azure AD for identity.

## Outcomes
All 9 plants live at M+17. Aggregate OEE visibility improved from weekly manual to 15-second update on shop-floor dashboards. Average OEE across plants rose 6.8 points in the first year (from 64.2 to 71.0). IATF 16949 surveillance audit passed with zero traceability findings — previously they averaged 3–4 minor findings per cycle.

## Lessons
PLC tag normalization is always the time sink — next time we scope 3x the nominal estimate for tag mapping. Regional Opcenter topology was right; a single global instance would not have met latency. Shop-floor change management (getting operators off paper travelers) took real investment; embedded plant champions were the difference maker.
