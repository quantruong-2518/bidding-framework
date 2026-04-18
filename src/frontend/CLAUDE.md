# frontend (Next.js 14) — AI Bidding Framework

> Local CLAUDE.md. Root config lives at `../../CLAUDE.md`. Read that first for project-wide rules. This file adds service-specific context.

## Role
- Next.js 14 App Router. Bid dashboard + workflow viewer (ReactFlow DAG of the 11-state machine) + real-time updates.
- Dev port `3000` (Docker host-mapped to `3001`).
- Upstream: user browser.
- Downstream: NestJS api-gateway REST (`NEXT_PUBLIC_API_URL`) + socket.io (`NEXT_PUBLIC_WS_URL` → `/ws`) + Keycloak (`NEXT_PUBLIC_KEYCLOAK_URL`, PKCE — stubbed in Phase 1).

## Delivery status (Phase 2.1)
- Workflow graph now covers the full S0→S11_DONE path, with S3a/b/c rendered as a parallel sibling row and a terminal short-circuit when `current_state === 'S11_DONE'` (every node marks `done`).
- `state-detail.tsx` side pane renders a bespoke panel per artifact: Bid Card / Triage / Scoping / BA Draft / SA Draft / Domain Notes / Convergence / HLD / WBS / Pricing / Proposal Package / Reviews / Submission / Retrospective. Each panel reads from `WorkflowStatus` (a single `GET /bids/:id/workflow/status` poll feeds all of them).
- **Phase 3.1:** `ProposalPanel` renders each proposal section in a native `<details>`/`<summary>` accordion with bodies piped through `react-markdown`. First section is `open` by default. `@tailwindcss/typography` is NOT installed, so `prose` classes are intentional forward-compatibility hints — they no-op today.
- **Phase 3.5:** `LangfuseLinkButton` on the bid detail header opens `/trace/<bidId>` on the self-hosted Langfuse (Docker profile `observability`). Hidden for non-admin roles AND when the gateway returns 404 (Langfuse not configured).
- `lib/api/types.ts` mirrors Python's artifact shapes (snake_case) to match the payload emitted by `src/ai-service/workflows/artifacts.py`. When Python adds a field, update the interface here first — that keeps the UI type-safe before the panel renders it.
- `lib/api/bids.ts::getWorkflowArtifact<T>(id, type)` hits the NestJS endpoint `GET /bids/:id/workflow/artifacts/:type` (14 allowed keys — see `ARTIFACT_KEYS` on the NestJS controller). Reserved for future lazy-load panels; no callers yet in Phase 2.1.

## Quick commands
```bash
# Install
npm install

# Dev
npm run dev

# Type check
npx tsc --noEmit -p tsconfig.json

# Tests (vitest)
npx vitest run
npx vitest           # watch

# Lint
npm run lint

# Production build
npm run build && npm start
```

## File tour (Phase 1)
```
frontend/
  next.config.mjs                # output: 'standalone' for Docker
  tailwind.config.ts, postcss.config.mjs
  tsconfig.json
  vitest.config.ts, vitest.setup.ts

  app/
    layout.tsx                   # root layout + Providers + globals.css
    providers.tsx                # QueryClientProvider (client component)
    page.tsx                     # redirects → /dashboard
    globals.css                  # Tailwind + CSS-var theme tokens
    login/page.tsx               # paste-JWT OR "Demo mode" (temp until Keycloak realm lands)
    api/health/route.ts          # /api/health for Docker healthcheck

    (authed)/                    # route group; ProviderGate bounces unauth → /login
      layout.tsx
      dashboard/page.tsx         # stats cards
      bids/page.tsx              # list (BidTable)
      bids/new/page.tsx          # create form
      bids/[id]/page.tsx         # detail — WorkflowGraph + Triage panel + state detail

  components/
    ui/                          # tiny shadcn-style primitives (no Radix): button, input, label, textarea, select, card, badge, dialog, separator, skeleton
    layout/
      sidebar.tsx, topbar.tsx
      provider-gate.tsx          # auth gate HOC
    bids/
      bid-card.tsx, bid-table.tsx
      create-bid-form.tsx        # react-hook-form + zod
      status-badge.tsx           # color by WorkflowState
      triage-review-panel.tsx    # approve/reject + optional bid-profile override
    workflow/
      workflow-graph.tsx         # ReactFlow DAG (S0..S11, S3a/b/c parallel row)
      state-timeline.tsx         # fallback vertical timeline (server-renderable)
      state-detail.tsx           # selected-state right pane

  lib/
    api/
      client.ts                  # fetcher adds Authorization: Bearer from zustand
      bids.ts                    # typed wrappers (listBids, createBid, trigger, …)
      types.ts                   # DTOs + zod schemas matching NestJS
    auth/
      store.ts                   # zustand — accessToken, user, setAuth, clearAuth
      keycloak-url.ts            # OIDC PKCE URL builder (wiring deferred)
    ws/
      socket.ts                  # singleton socket.io-client per token
      use-bid-events.ts          # hook: subscribe/unsubscribe + query-cache invalidate on bid.event
    hooks/
      use-bids.ts                # TanStack Query hooks
      query-keys.ts
    utils/
      cn.ts                      # clsx + tailwind-merge
      state-palette.ts           # SINGLE SOURCE: WorkflowState → {label, description, tone}

  __tests__/
    state-palette.test.ts
    bid-card.test.tsx
    workflow-graph.test.tsx      # mocks reactflow primitives
    use-bid-events.test.ts       # mocks socket.io-client

  .env.example                   # NEXT_PUBLIC_* keys
```

## Conventions (reinforces root CLAUDE.md)
- **Server Components by default.** Only add `'use client'` when the module needs state, effects, browser APIs, or third-party client-only libs (ReactFlow, socket.io-client, zustand, react-query, react-hook-form).
- kebab-case for routes + file basenames, PascalCase for React components (file still kebab-case).
- Tailwind utility classes (+ CVA for variants). No inline styles.
- Zustand for client state (auth token, ephemeral UI state).
- TanStack Query for server state. Mutations must invalidate affected query keys.
- Zod for runtime validation at system boundaries (API responses, form inputs).

## Contract with NestJS
- REST: all non-`/health` calls require `Authorization: Bearer <token>` — injected by `lib/api/client.ts`.
- Payloads are **camelCase** on the outbound NestJS DTO layer. But artifact payloads returned by `/workflow/status` + `/workflow/artifacts/:type` are **snake_case** — NestJS forwards the ai-service body verbatim. The interfaces in `lib/api/types.ts` reflect that (`ba_draft`, `sa_draft`, etc.).
- WebSocket: `/ws` namespace, auth via `{auth:{token}}`. Emit `subscribe`/`unsubscribe` with bidId. Listen for `bid.event` + `bid.broadcast`.
- Workflow state literals must match Python: `S0, S1, S1_NO_BID, S2, S2_DONE, S3, S4..S11, S11_DONE`. `state-palette.ts` is the single source — update there + in `workflow-graph.tsx::mainOrderForCompare` when a new state ships.
- Artifact keys accepted by `/workflow/artifacts/:type`: `bid_card, triage, scoping, ba_draft, sa_draft, domain_notes, convergence, hld, wbs, pricing, proposal_package, reviews, submission, retrospective` (14 total). See `ARTIFACT_KEYS` on the NestJS controller for the source of truth.

## Known gotchas
- Demo-mode token (`demo-token` injected by login page) will be rejected by NestJS `JwtAuthGuard` since the Keycloak realm isn't provisioned yet. UI renders correctly; live data fetches 401 until the realm lands.
- ReactFlow requires `'use client'` + fixed-height parent. Respect that when adding new layouts.
- `NEXT_PUBLIC_WS_URL` can be `http://…` — socket.io-client upgrades to WebSocket automatically. Match the NestJS origin.
- Build uses `output: 'standalone'` for Docker — keep `public/` existing (can be empty).
- Dark mode is driven by `.dark` on `<html>`; no toggle yet.
- `Triage` interface in `lib/api/types.ts` matches Python `TriageDecision` (`recommendation: 'BID' | 'NO_BID'` + `overall_score: 0-100` + `score_breakdown: Record<string, number>` + `rationale`). Closed the Phase 2.1 shape mismatch in the Phase 2 closure audit (2026-04-18). The reviewer panel + `state-detail.tsx::TriagePanel` render those fields directly.
- `workflow-graph.tsx::mainOrderForCompare` MUST include every terminal literal (`S2_DONE`, `S11_DONE`, `S1_NO_BID`) the workflow can settle on, otherwise `currentIdx = -1` and every node renders as `pending`. Add new terminals there when they ship.

## Pointers
- Root rules: `../../CLAUDE.md`
- Full architecture: `../../docs/architecture/SYSTEM_ARCHITECTURE.md`
- NestJS contract: `../api-gateway/CLAUDE.md`
- State labels / colors: `lib/utils/state-palette.ts`
- Current progress: `../../CURRENT_STATE.md`
