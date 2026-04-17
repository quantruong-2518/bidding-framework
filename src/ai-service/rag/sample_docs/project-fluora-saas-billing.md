---
project_id: proj-fluora-021
client: Fluora
domain: saas
year: 2024
doc_type: case-study
---
# Fluora — Usage-Based Billing Platform

## Context
Fluora, a B2B observability SaaS, was shifting from a flat-fee tier model to metered usage billing (events ingested, GB scanned, alert minutes). Their existing Stripe subscription integration could not represent the pricing model, revenue recognition under ASC 606 was a month-end spreadsheet, and finance was spending 7 business days on the close. We delivered a usage-based billing + revenue platform in 5 months.

## Approach
Three services: a Meter (Kafka -> ClickHouse) that ingested product usage events with idempotency keys and a 48h late-arrival tolerance; a Rater that joined meter rollups with entitlement plans to produce line-item charges; and a Biller that pushed invoices to Stripe and reported revenue to NetSuite via a nightly SuiteAnalytics Connect feed. Because usage data can arrive late, we froze a billing period 3 business days after close and post-adjusted in the subsequent period with a dedicated "late usage" SKU to keep audit trails clean.

## Tech Stack
Kafka (Redpanda), ClickHouse, Go for Meter + Rater, Node.js for Biller, Stripe Billing for invoicing + dunning, NetSuite SuiteAnalytics Connect for GL sync, Temporal for close orchestration, Grafana for ops dashboards, AWS (MSK, EKS, RDS PostgreSQL for entitlement).

## Outcomes
Month-end close dropped from 7 business days to 1.5. Average invoice error rate (measured by finance adjustment volume) fell 91%. ASC 606 revenue recognition moved from spreadsheet to audited pipeline; the FY24 external audit closed with no rev-rec findings. Net revenue retention tracking now lives in ClickHouse and refreshes hourly.

## Lessons
Late-arriving usage is the hard problem in metered billing; investing up front in the late-usage SKU pattern saved months of downstream pain. ClickHouse schema evolution needs strict governance — we almost shipped a breaking meter change in month 4. Stripe's metered billing API was not expressive enough for our tiered-per-SKU rules; we bill off-platform and push Stripe the final line items.
