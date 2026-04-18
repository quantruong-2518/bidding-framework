# api-gateway (NestJS) — AI Bidding Framework

> Local CLAUDE.md. Root config lives at `../../CLAUDE.md`. Read that first for project-wide rules. This file adds service-specific context.

## Role
- NestJS 10 (TypeScript) API gateway. Authentication + RBAC + request validation + WebSocket fanout + bids CRUD + workflow proxy to ai-service.
- Listens on port `3000`.
- Upstream: frontend (Next.js) at `http://localhost:3001` (browser), websocket namespace `/ws`.
- Downstream: ai-service (`http://ai-service:8001`), Redis (`redis:6379`), Keycloak (`keycloak:8080`), Postgres (future).

## Quick commands
```bash
# Install
npm install

# Dev (watch mode)
npm run start:dev

# Build
npm run build

# Unit tests (rootDir=src, picks app.controller.spec.ts)
npm test

# E2E / controller specs (picks test/*.spec.ts — bids + workflows)
npm run test:e2e

# Lint / format
npm run lint
```

## File tour (Phase 1)
```
api-gateway/
  package.json               # deps incl. @nestjs/*, passport-jwt, jwks-rsa, ioredis, @nestjs/axios, socket.io, jsonwebtoken
  nest-cli.json
  tsconfig.json, tsconfig.build.json
  Dockerfile                 # multi-stage node:20-alpine

  src/
    main.ts                  # global validation pipe, Helmet, CORS from CORS_ORIGIN
    app.module.ts            # wires Auth + Bids + Workflows + Redis + Events modules;
                             # registers JwtAuthGuard + RolesGuard as APP_GUARD
    app.controller.ts        # GET /health (@Public)

    auth/
      auth.module.ts
      jwt.strategy.ts        # passport-jwt + jwks-rsa → {KEYCLOAK_ISSUER}/protocol/openid-connect/certs
      jwt-auth.guard.ts      # extends AuthGuard('jwt'), honors @Public()
      roles.guard.ts         # checks request.user.roles vs @Roles(...)
      public.decorator.ts    # @Public() — skip JWT
      roles.decorator.ts     # @Roles('admin','bid_manager','ba','sa','qc')
      current-user.decorator.ts

    bids/
      bid.entity.ts          # in-memory shape (swap-point for Postgres in Phase 2)
      bids.service.ts        # Map-backed repo
      bids.controller.ts     # POST / GET / PATCH / DELETE with role gating
      create-bid.dto.ts, update-bid.dto.ts  # class-validator DTOs

    workflows/
      workflows.service.ts   # proxies to ai-service; camelCase → snake_case body transform
                             # trigger() → POST /workflows/bid/start-from-card
                             # sendTriageSignal() → /{wfId}/triage-signal
                             # getStatus() → GET /{wfId}
      workflows.controller.ts
      triage-signal.dto.ts, trigger-workflow.dto.ts

    gateway/
      events.gateway.ts      # socket.io /ws; JWT handshake (auth.token OR Authorization header)
                             # per-bid rooms (bid:{id}); emits bid.event + bid.broadcast
      events.module.ts

    redis/
      redis.service.ts       # two ioredis clients (publisher + subscriber); XADD + PUBLISH
      redis.module.ts        # @Global()

  test/
    bids.controller.spec.ts
    workflows.controller.spec.ts
    jest-e2e.json            # config used by npm run test:e2e
```

## Conventions (reinforces root CLAUDE.md)
- kebab-case filenames (NestJS standard)
- NestJS idioms: modules + controllers + services; `@Injectable()`; constructor DI
- DTOs with `class-validator` decorators; `ValidationPipe({whitelist:true, transform:true})` globally
- Use `Logger` injected per service — never `console.*`
- Controllers stay thin — delegate to services
- Role guards come from metadata via `@Roles(...)`; `@Public()` opts out of JWT

## Auth contract
- Every non-`/health` route requires `Authorization: Bearer <keycloak-access-token>` (RS256, audience `KEYCLOAK_CLIENT_ID=bidding-api`, issuer `{KEYCLOAK_ISSUER}`)
- **Phase 3.2a:** Realm `bidding` is now provisioned via `src/keycloak/bidding-realm.json` + `start-dev --import-realm`. `JwtStrategy` hard-codes `EXPECTED_AUDIENCE = 'bidding-api'` (not from env anymore); the `bidding-frontend` client has an audience mapper that injects `bidding-api` into every access token. If you see `Invalid audience` / 401s, check the mapper + the realm import.
- Roles on the JWT: `realm_access.roles` → `['admin','bid_manager','ba','sa','qc']`

## REST surface (Phase 1)
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/health` | public | |
| POST | `/bids` | admin, bid_manager | |
| GET | `/bids` | any auth | |
| GET | `/bids/:id` | any auth | |
| PATCH | `/bids/:id` | admin, bid_manager | |
| DELETE | `/bids/:id` | admin | |
| POST | `/bids/:id/workflow` | admin, bid_manager | Proxies to ai-service `/start-from-card` |
| POST | `/bids/:id/workflow/triage-signal` | admin, bid_manager, ba, sa, qc | |
| GET | `/bids/:id/workflow/status` | any auth | |

## WebSocket (`/ws`)
- Connect with `{auth:{token}}` or `Authorization: Bearer`
- Client emits: `subscribe` / `unsubscribe` (payload: `bidId`)
- Server emits: `bid.event` (room `bid:{id}`) — from Redis channel `bid.events.channel.{bidId}`
- Server emits: `bid.broadcast` — fleet-wide from Redis `bid.events.channel.broadcast`

## Known gotchas
- Default `npm test` uses Jest `rootDir=src` and picks up only `src/**/*.spec.ts` (just `app.controller.spec.ts`). Run `npm run test:e2e` to execute the 8 controller specs under `test/`.
- `WorkflowsService.trigger` expects the `BidCard` contract defined in Python (`ai-service/workflows/models.py::BidCard`). Keep field names in sync if models evolve.
- CORS defaults to `*` when `CORS_ORIGIN` unset — tighten before any shared deploy.
- In-memory bid store — data loss on restart. Replace with TypeORM/Prisma + Postgres in Phase 2.

## Pointers
- Root rules: `../../CLAUDE.md`
- Full architecture: `../../docs/architecture/SYSTEM_ARCHITECTURE.md`
- Contract with ai-service: see `../../docs/architecture/SYSTEM_ARCHITECTURE.md` "Cross-service contracts"
- Current progress: `../../CURRENT_STATE.md`
