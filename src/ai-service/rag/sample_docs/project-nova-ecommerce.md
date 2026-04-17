---
project_id: proj-nova-014
client: NovaRetail
domain: e-commerce
year: 2024
doc_type: case-study
---
# NovaRetail — Headless Commerce Replatform

## Context
NovaRetail operated three brand storefronts on a shared Magento 2 monolith. Peak-hour p95 was 3.8s on PLP, checkout conversion lagged the category benchmark by 1.6pp, and release cadence had degraded to one deploy every 9 days due to cross-brand regressions. The mandate was a 9-month replatform to a headless stack while keeping all three storefronts live.

## Approach
Strangler-fig migration behind a Cloudflare Worker edge router. Per route (category, PDP, cart, checkout, account) we shipped a Next.js App Router implementation backed by commercetools, routed a percentage of traffic via the Worker, watched the RUM dashboard, and ramped. Checkout went last — only after all upstream routes were stable — because it had the strictest compliance review (PCI SAQ A-EP). A shared design-system package (Radix primitives + tokens) let the three brands share 80% of components while theming diverged at the token layer.

## Tech Stack
Next.js 14 (App Router, RSC), commercetools (catalog + cart + orders), Algolia (search + browse), Stripe (payments), Cloudflare Workers + KV (edge routing, A/B), Contentful (editorial), Segment + Snowflake (analytics), GitHub Actions + Vercel preview environments.

## Outcomes
PLP p95 down to 780ms. Checkout conversion up 2.3pp (crossed benchmark). Deploy cadence up to ~11/day across the three brands. Total traffic cutover finished at M+8 — 4 weeks ahead of plan — and the Magento monolith was decommissioned a month later.

## Lessons
The edge-router strangler approach was the winning call — we could roll back any route in <60s during the whole migration. Contentful modeling took two false starts; next time we'd lock content model before any component work. Algolia index rebuild cost was higher than forecast once we added personalization, which we hadn't sized.
