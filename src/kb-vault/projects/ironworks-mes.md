---
project_id: proj-ironworks-031
client: IronworksMfg
domain: manufacturing
year: 2023
doc_type: project
tags: [mes, iiot, opc-ua, shop-floor]
---
# IronworksMfg — Manufacturing Execution System

## Context
IronworksMfg operates 6 steel fabrication plants producing structural assemblies for rail and infrastructure. Production scheduling lived in spreadsheets, shop-floor data was hand-keyed into SAP at shift end, and yield analysis ran a week behind real time. We delivered a modern MES unifying scheduling, dispatch, quality, and OEE.

## Approach
Edge nodes per plant running lightweight [[microservices]] on [[kubernetes]] (k3s) ingest OPC-UA signals from PLCs and CNC controllers. An event gateway normalizes to a canonical shop-floor event stream and replicates to the central cloud. SAP integration happens via IDoc over a mirrored IDoc bus — production orders in, confirmations out, materials consumption in real time. The scheduling engine uses constraint programming (OR-Tools) re-run every 15 minutes.

## Tech Stack
k3s at the edge, EKS in the cloud, Kafka MirrorMaker for edge-to-cloud replication, OR-Tools CP-SAT, Angular front-end for shop-floor tablets, SAP ECC 6.0 via PI/PO. Observability: Prometheus federated from edge clusters.

## Outcomes
OEE improved 14pp across the pilot plant in the first quarter, 9-11pp across the remaining five by M+12. Scrap rate down 22%. Schedule adherence up from 71% to 94%.

## Lessons
OPC-UA namespaces are never as standardized as vendors claim — plan a dedicated mapping sprint per plant. See [[estimation-pitfalls]] for how we learned to budget that.
