# frontend (Next.js 14) — AI Bidding Framework

> Local CLAUDE.md. Root config lives at `../../CLAUDE.md`. Read that first for project-wide rules. This file adds service-specific context.

## Role
- Next.js 14 App Router. Bid dashboard + workflow viewer (ReactFlow DAG of the 11-state machine) + real-time updates.
- Dev port `3000` (Docker host-mapped to `3001`).
- Upstream: user browser.
- Downstream: NestJS api-gateway REST (`NEXT_PUBLIC_API_URL`) + socket.io (`NEXT_PUBLIC_WS_URL` → `/ws`) + Keycloak (`NEXT_PUBLIC_KEYCLOAK_URL`, PKCE — stubbed in Phase 1).

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
- Payloads are **camelCase** (NestJS DTO convention). The gateway transforms to snake_case when proxying to ai-service.
- WebSocket: `/ws` namespace, auth via `{auth:{token}}`. Emit `subscribe`/`unsubscribe` with bidId. Listen for `bid.event` + `bid.broadcast`.
- Workflow state literals must match Python: `S0, S1, S1_NO_BID, S2, S2_DONE, S3..S11`. `state-palette.ts` is the single source — update there when new states ship.

## Known gotchas
- Demo-mode token (`demo-token` injected by login page) will be rejected by NestJS `JwtAuthGuard` since the Keycloak realm isn't provisioned yet. UI renders correctly; live data fetches 401 until the realm lands.
- ReactFlow requires `'use client'` + fixed-height parent. Respect that when adding new layouts.
- `NEXT_PUBLIC_WS_URL` can be `http://…` — socket.io-client upgrades to WebSocket automatically. Match the NestJS origin.
- Build uses `output: 'standalone'` for Docker — keep `public/` existing (can be empty).
- Dark mode is driven by `.dark` on `<html>`; no toggle yet.

## Pointers
- Root rules: `../../CLAUDE.md`
- Full architecture: `../../docs/architecture/SYSTEM_ARCHITECTURE.md`
- NestJS contract: `../api-gateway/CLAUDE.md`
- State labels / colors: `lib/utils/state-palette.ts`
- Current progress: `../../CURRENT_STATE.md`
