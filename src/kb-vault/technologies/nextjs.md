---
doc_type: technology
domain: frontend
tags: [frontend, react, ssr]
---
# Next.js

## Capability Summary
React framework with App Router, React Server Components, and first-class edge deployment. Our default choice for customer-facing web where SEO, TTFB, or progressive disclosure matters.

## Where we have delivered
- [[nova-commerce-platform]] — three brands, App Router + RSC, strangler migration off Magento.
- [[vesta-onboarding]] — single-page onboarding flow orchestrated by [[temporal-io]] on the backend.

## Patterns we use
- RSC for data-heavy, low-interactivity pages; client components only for islands of interactivity.
- Route Handlers as thin edge gateways, never as the business layer.
- Vercel preview environments per PR for design review.

## Integration notes
- Authenticated flows should not use `getServerSession`-style patterns on the edge — validate JWTs at a gateway (NestJS / Cloudflare Worker) and forward identity as a header.
