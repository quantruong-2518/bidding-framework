---
doc_type: lesson
domain: delivery
tags: [integration, risk, lessons]
---
# Integration Risks

## Purpose
Recurring integration hazards we have tripped on. Use as a pre-load for the risk register on every bid that touches one of these patterns.

## Mainframe CDC
Source: [[acme-core-banking]]. Kafka Connect JDBC offset tracking against mainframe tables is fragile under load. Prefer a purpose-built mainframe CDC agent (IBM InfoSphere, Attunity, Precisely Connect).

## HL7 v2 ambiguity
Source: [[medix-emr-2024]]. HL7 v2 "standard" is a forest of local dialects. Budget discovery time per interface partner; never assume two hospitals' v2 feeds are compatible.

## Edge-to-cloud replication backpressure
Source: [[ironworks-mes]]. When plants lose connectivity, edge event buffers fill. Design replication with explicit backpressure and retention, not hope. MirrorMaker default retention is *not* what you want.

## Personalization cost in commerce search
Source: [[nova-commerce-platform]]. Algolia index rebuilds scale non-linearly once personalization fields are added. Size the index-rebuild compute on the final personalization schema, not the MVP schema.

## Core-banking write coupling
Source: [[vesta-onboarding]] + [[acme-core-banking]]. Every integration that writes to a core-banking system needs idempotency keys AND a client-side reconciliation loop, even if the vendor claims both are unnecessary.

## Identity federation with legacy IdPs
Source: multiple. Legacy PingIdentity / Siteminder tenants rarely expose OIDC cleanly. Plan a SAML shim; do not promise pure-OIDC on day one.

## TM Forum / ONAP mapping
Source: [[telora-5g-bss]]. TM Forum Open API models don't map 1:1 to any real BSS implementation. Treat the TMF layer as a facade, not a schema.
