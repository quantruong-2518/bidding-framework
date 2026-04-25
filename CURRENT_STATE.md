# CURRENT STATE — AI Bidding Framework

> File này dùng để track tiến độ. Mỗi conversation mới đọc file này trước.
> Cập nhật mỗi khi hoàn thành 1 task.

## Last Updated: 2026-04-25 (Phase 3.3 delivered + post-review hardening — 289 tests green, ACL drift guarded)

## Overall Status: PHASE 3.5 + 3.1 + 3.2a + 3.2b + 3.3 (code, hardened) COMPLETE — code-only $0 work exhausted; next branch picks one external resource

## >>> NEXT ACTION <<<
**Open `memory/project_next_steps_post_conv10.md` first** — it has the branch picker, preconditions, acceptance criteria, and a code-only tactical-cleanup option for when no resources are available.

**Quick decision tree:**
- ✅ `ANTHROPIC_API_KEY` + Docker → **Conv-8c** (40 min, ~$0.10, closes 4 carry-forwards: Phase 2.2 real-LLM + 3.5 Langfuse + 3.2b live + 3.3 live).
- ✅ `ANTHROPIC_API_KEY` only (no Docker) → design work for Conv-11 Phase 3.4 (real S11 retrospective + multi-tenant Qdrant); LLM-needing parts blocked.
- ✅ K8s cluster + k6 runner → **Conv-12** (Phase 3.6 + 3.7 — Helm + load test).
- ❌ None of the above → **tactical cleanup commit**: per-bid cost fanout in `recentBids`, silent token refresh + logout UI, frontend `/audit` admin gate, `.env.example` rebuild. Three to four batch into one commit; no one of them blocks pilot.

**Conversation 2026-04-25 recap (read if you weren't in the previous conversation):** see `memory/project_conv_2026_04_25_log.md` — three commits, 65 files, +6 359 LOC across Phase 3.2b + 3.3 + post-review hardening. 18 pytest / 190 jest / 81 vitest. No phase ships unverified at the unit level; Docker smokes are the carry-forward.

**Roadmap:** `project_phase_3_roadmap.md` (7 sub-tasks / ~7 conversations; MVP-pilot path 3.5 → 3.1 → 3.2a → 3.6; post-pilot 3.2b → 3.3 → 3.4 → 3.7; only 3.6 + 3.7 block on external infra).

**Per-task plans (read the one for the next conversation, not all at once):**

| Conv | Task | Plan | Scope | External dep |
|---|---|---|---|---|
| 6 | 3.5 Langfuse | `project_phase_3_5_detailed_plan.md` | 12 decisions, 21 steps, ~500 LOC | $0 |
| 7 | 3.1 Jinja templates | `project_phase_3_1_detailed_plan.md` | 10 decisions, 22 steps, ~800 LOC | $0 |
| 8 | 3.2a Keycloak + live-LLM smoke | `project_phase_3_2a_detailed_plan.md` | 12 decisions, 18 steps, ~500 LOC | $0 (+ ANTHROPIC_API_KEY for smoke) |
| 9 | 3.2b RBAC + audit log + bids→Postgres | `project_phase_3_2b_detailed_plan.md` | 12 decisions, 24 steps, ~1200 LOC | $0 |
| 10 | 3.3 Audit dashboard | `project_phase_3_3_detailed_plan.md` | 12 decisions, 18 steps, ~1200 LOC | $0 (reads 3.5 + 3.2b) |
| 11 | 3.4 Retrospective + multi-tenant | `project_phase_3_4_detailed_plan.md` | 12 decisions, 26 steps, ~1000 LOC | ~$0.01–0.05/bid |
| 12 | 3.6 K8s (Helm) + 3.7 Load test (k6) | `project_phase_3_6_detailed_plan.md` + `project_phase_3_7_detailed_plan.md` | ~2100 LOC combined | $$ cluster + $ runner |

**Dependency order locked:**
- 3.5 before real LLM (observability-first)
- 3.2a before 3.2b (realm is RBAC foundation)
- 3.5 + 3.2b before 3.3 (dashboard reads from both)
- 3.4 closes Phase 2.7 kb-vault carry-forward (multi-tenant filter enables prior-bid RAG)
- 3.6 before 3.7 (load test needs real cluster target)

**Each plan has:** scope + non-goals + locked decisions table + contract tables (DTOs, endpoints, schemas) + file-level breakdown (NEW + MODIFIED) + step-by-step execution order (grouped by phase) + test matrix + risk register + cost gate + runbook.

### Phase 3.2b + 3.3 Post-Review Hardening — Conv-10 solo (2026-04-25, same day)
**Trigger:** code review of the just-shipped Phase 3.2b + 3.3 surfaced 2 real runtime bugs + 6 contract / coverage gaps. All addressed in one follow-up commit. No external deps. Zero shipped behaviour was wrong; this round is "kill the easy regressions before pilot".

**Bugs fixed:**
1. **`audit_log` flood from polling** — frontend `useWorkflowStatus` polls every 15 s; Phase 3.2b had attached `@Roles(...)` to `/workflow/status`, so each poll wrote a row. 1 user × 1 bid × 24 h = ~5 760 rows of noise. Fix: new `@SkipAudit()` metadata decorator (`src/audit/skip-audit.decorator.ts`); interceptor reads it via `Reflector.getAllAndOverride`. Applied at handler level on `WorkflowsController.status` and class level on `AuditDashboardController` (so `/dashboard/*` reads — including the cross-bid view itself — don't self-reference).
2. **Langfuse `aggregateRange` sequential N+1** — for-await loop over up to 200 traces × ~200–500 ms each → 40–100 s per cold call (worse than the 5-min cache TTL window in pathological cases). Fix: extracted `chunkedMap` helper (concurrency=10) inside `langfuse.aggregator.ts`. Preserves input order, rethrows first rejection, default cap is configurable. Wallclock now ~200 ms × ⌈N/10⌉.

**Contract clean-ups (zero broken — no client code consumed the dropped fields):**
3. `DashboardSummary.totals.blocked` → `inProgress` — semantic mislabel; `blocked = DRAFT` was wrong (DRAFT means "not yet triggered", not "blocked"). New `inProgress` covers DRAFT + TRIAGED + IN_PROGRESS. Frontend type updated; KPI cards still render fine.
4. `DashboardSummary.topBids` → `recentBids` — old field claimed "top by cost" but `costUsd` was hard-coded to 0 and ordering was newest-first. Renamed + dropped the misleading cost field. Per-bid cost fanout deferred behind a follow-up note.
5. `DashboardSummary.costUsd.p95PerBid` — dropped (always 0; needs per-bid fanout).
6. `summaryToCsv` footer key renamed `# totals.blocked=` → `# totals.in_progress=`.
7. **Self-referential decision feed** — `recentDecisions` now filters out `GET /dashboard/*` and `GET /bids/:id/audit` so an admin loading the dashboard doesn't see themselves doing it.
8. **`getBidDetail.summary.{completedAt, totalDurationMs}`** — was scanning `decisionTrail` for "workflow"-containing actions (fragile + included status reads). New rule: terminal-only (`status === 'WON' | 'LOST'`), `completedAt = bid.updatedAt`, otherwise `null`. Cleaner contract; covered by 1 new spec.

**Coverage / drift fixes:**
9. **`apply_role_filter` extracted** to `workflows/acl.py` (was inline in router.py). Decouples the BidState scrubbing from FastAPI / Temporal / parser imports so it runs on bare Python. New `tests/test_role_filter.py` covers admin / empty / ba / qc / domain_expert / multi-role-union / `reviews=[]` invariant / idempotence — 7 specs, all green.
10. **ACL drift guard** — `src/shared/acl-map.json` is now the canonical contract. Pytest `test_canonical_json_matches_source` checks Python's `acl_as_json()` matches the file; Jest `acl-canonical.spec.ts` checks NestJS `FALLBACK_ARTIFACT_ACL` matches the file. Update procedure documented in `src/shared/README.md`. Any drift → both sides red until reviewer realigns the JSON.

**Files touched:**
- ai-service: `workflows/acl.py` (added `apply_role_filter`), `workflows/router.py` (uses helper, tightened imports), `tests/test_acl.py` (+1 drift case), `tests/test_role_filter.py` NEW (7 specs).
- api-gateway: `audit/skip-audit.decorator.ts` NEW, `audit/audit.interceptor.ts` (reads SKIP_AUDIT_KEY), `workflows/workflows.controller.ts` (`@SkipAudit()` on status), `audit-dashboard/audit-dashboard.controller.ts` (`@SkipAudit()` class-level), `audit-dashboard/audit-dashboard.service.ts` (totals.inProgress, recentBids, terminal-only duration, decision-feed filter), `audit-dashboard/aggregators/langfuse.aggregator.ts` (chunkedMap + parallel), `audit-dashboard/types.ts` (contract clean-up), `test/audit.interceptor.spec.ts` (+2 SkipAudit cases), `test/audit-dashboard.service.spec.ts` (+3 cases: terminal duration / inProgress count / self-ref filter), `test/audit-dashboard.controller.spec.ts` (rename), `test/langfuse-aggregator.spec.ts` NEW (4 chunkedMap cases), `test/acl-canonical.spec.ts` NEW (3 drift cases).
- frontend: `lib/api/audit.ts` (rename fields), `__tests__/audit-dashboard.test.tsx` (rename fixture).
- shared: `shared/acl-map.json` NEW, `shared/README.md` NEW.

**Tests at delivery:**
- ai-service pytest: **18 passed / 2 files** (10 ACL incl. drift + 8 role-filter incl. helper).
- api-gateway jest: **190 passed / 14 suites** (+12 from 3.3 baseline 178).
- frontend vitest: **81 passed / 14 suites** (unchanged; field renames only touched fixtures).
- `npm run build` (api-gateway + frontend) + `tsc --noEmit` clean.

**Open carry-forward (unchanged from 3.3):**
- Live Docker smoke with Langfuse creds.
- Temporal Visibility gRPC client in Phase 3.6.
- Per-bid cost fanout (now `recentBids` doesn't lie about it).
- Full `pytest` regression (temporalio + jinja2 + anthropic + langgraph) — Docker-only.

### Phase 3.3 Delivery — Conv-10 solo (2026-04-25)
**Scope:** Audit + cost dashboard stitching three upstreams (Postgres `audit_log` from 3.2b, Langfuse REST API, Temporal Visibility). Per-bid drill-down + cross-bid summary + recharts cost panels + CSV export. Partial-failure tolerant — every upstream miss adds a string to `warnings[]` rather than failing the response. No external deps, $0 cost (reads sources that already exist). Conv-10 solo.

**New files (api-gateway) — audit-dashboard module:**
- `src/audit-dashboard/types.ts` — contract DTOs (`BidAuditDetail`, `DashboardSummary`, `CostsResponse`, helpers).
- `src/audit-dashboard/cache.ts` — `TtlCache` LRU wrapper, 5-minute TTL, keyed by normalised query string. Used by service for all 3 endpoints.
- `src/audit-dashboard/aggregators/audit-log.aggregator.ts` — TypeORM reads on `audit_log`: `forBid(bidId)` (500-row per-bid chronological), `recent(range, role?)`, `distinctBidCount(range)` (raw SQL DISTINCT COUNT).
- `src/audit-dashboard/aggregators/langfuse.aggregator.ts` — REST-only integration. `forBid` lists traces by `tags[]=bid_id` then walks per-trace GENERATION observations; `aggregateRange` sweeps the date window. Returns zero-values + warning when `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` unset. Exports pure helper `summariseObservations(obs[])` for unit tests.
- `src/audit-dashboard/aggregators/temporal.aggregator.ts` — **stub** returning `{events: [], warning: "Temporal Visibility integration is stubbed (lands with Phase 3.6 K8s)."}`. Interface preserved so Phase 3.6 can drop in `@temporalio/client` without touching the service layer.
- `src/audit-dashboard/audit-dashboard.service.ts` — `getBidDetail`, `getSummary`, `getCosts`, `summaryToCsv`. Every method uses `Promise.allSettled` → warnings[] accumulates rejections; admin never sees a 500 because one upstream flapped.
- `src/audit-dashboard/audit-dashboard.controller.ts` — 4 endpoints: `GET /bids/:id/audit` (admin+bid_manager+qc), `GET /dashboard/audit` (admin), `GET /dashboard/audit.csv` (admin, `Content-Type: text/csv`), `GET /dashboard/costs` (admin). Date validator enforces `YYYY-MM-DD`; default range is the last 30 days.
- `src/audit-dashboard/audit-dashboard.module.ts` — wires TypeORM + HttpModule + BidsModule, exports `AuditDashboardService` for future reuse.
- `test/audit-dashboard.service.spec.ts` — 10 Jest cases: bid detail merge, partial-failure warnings, NotFoundException propagation, TTL cache, summary aggregation + filter, Langfuse-unconfigured warning, invalid-date reject, CSV serializer (header + row + footer comments), `summariseObservations` (per-agent + per-model + p95 latency + empty-input edge).
- `test/audit-dashboard.controller.spec.ts` — 7 Jest cases: detail round-trip, filter params pass-through, default range, 400 on bad date, CSV content, groupBy normalisation, valid groupBy preserved.

**Modified (api-gateway):**
- `package.json` — added `lru-cache ^10.4.3`. No SDK deps added (`@temporalio/client` deferred; Langfuse via HttpService).
- `src/app.module.ts` — registers `AuditDashboardModule`.

**New files (frontend):**
- `lib/api/audit.ts` — typed `fetchBidAudit`, `fetchSummary`, `downloadCsv` (blob + `<a download>`), `buildCsvUrl` helper.
- `components/audit/cost-chart.tsx` — dual recharts panel: daily `BarChart` + per-agent `PieChart`. Tolerates empty data with placeholder copy.
- `components/audit/decision-trail.tsx` — flat table of audit rows, status-code coloured (≥500 red, ≥400 amber, 2xx emerald).
- `components/audit/audit-timeline.tsx` — interleaves decisions + Temporal events on a vertical track, chronological.
- `components/audit/workflow-history-view.tsx` — `<details>` collapsibles per event; empty state shows the warning from the server response.
- `app/(authed)/audit/page.tsx` — cross-bid dashboard: filters form (`from`/`to`/`status`/`profile`/`client`), 4 KPI cards, cost chart, decision trail, warnings banner, CSV export button. TanStack Query with `staleTime: 60s`.
- `app/(authed)/audit/[bidId]/page.tsx` — per-bid detail: 4 KPI cards, timeline, side-by-side decision trail + workflow history.
- `__tests__/audit-dashboard.test.tsx` — 8 vitest cases (4 page render + 2 DecisionTrail + 2 WorkflowHistoryView) with a `vi.mock('recharts', ...)` passthrough so jsdom doesn't choke on ResizeObserver.

**Modified (frontend):**
- `package.json` — added `recharts ^2.15.0`.
- `components/layout/sidebar.tsx` — new `Audit` nav item, hidden when `roles` lacks `admin`.

**Contract tables:**

| Endpoint | Roles | Query | Response |
|---|---|---|---|
| `GET /bids/:id/audit` | admin, bid_manager, qc | `:id` UUID | `BidAuditDetail` |
| `GET /dashboard/audit` | admin | `from/to/role/status/profile/client/page/limit` | `DashboardSummary` |
| `GET /dashboard/audit.csv` | admin | same filters | `text/csv` string |
| `GET /dashboard/costs` | admin | `from/to/groupBy=agent\|bid\|state` | `CostsResponse` |

**Tests at delivery:**
- api-gateway jest: **178 passed / 12 suites** (+17 from 3.2b baseline: 10 service + 7 controller). Build + tsc clean.
- frontend vitest: **81 passed / 14 suites** (+8 audit-dashboard). `tsc --noEmit` clean. `next build` emits `/audit` 109 kB + `/audit/[bidId]` 4.2 kB. First Load JS shared 87.4 kB (no regression — recharts ships only on `/audit`).
- ai-service pytest: **10 ACL cases** unchanged (no Python edits this phase).
- `docker compose config` parses.

**Plan → delivery deviations (locked in code):**
- Temporal aggregator shipped as a stub. Plan called for `@temporalio/client`-based `ListWorkflowExecutions` + history walk. Host has no Docker + the dep is heavy; stub pattern keeps the interface stable so Phase 3.6 (K8s) is a drop-in. Per-bid page shows the warning in a `<div role="alert">` placeholder.
- Langfuse integration uses plain `HttpService` + REST, not the `langfuse-node` SDK. Same data, one fewer dep, tests mock the aggregator directly.
- Per-bid cost lookup in the cross-bid summary (`topBids[].costUsd`) is left at 0 — a real per-bid breakdown requires N upstream Langfuse queries per summary render. Plan accepted this as deferrable.
- `groupBy=bid|state` on `/dashboard/costs` returns empty buckets + warning. Agent grouping is the operational default; other slices land when ops request them.

**Carry-forward (needs Docker + creds):**
- Live smoke: boot stack with `LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY` set, drive a bid, open `/audit/<bidId>`, verify `decisionTrail` populated + `costs.totalUsd > 0` + `warnings` only contains the Temporal stub note.
- Full `pytest` regression (temporalio + jinja2 + anthropic + langgraph) — unchanged from Phase 3.2b carry-forward.
- Temporal Visibility integration in Phase 3.6 (swap the stub for a gRPC client bound to the in-cluster Temporal frontend).
- Per-bid cost per N-query fanout (can add with server-side cache).

**Known gotchas introduced:**
- `recharts` in jsdom throws on `ResizeObserver`. `audit-dashboard.test.tsx` declares `vi.mock('recharts', ...)` returning passthrough components so the chart panels can render without crashing; assertions still verify labels + KPI numbers that live outside the charts.
- `downloadCsv` fetches the CSV via blob (not `window.open`) so the Bearer token rides along. A vitest case covers that the button calls into the helper.
- Audit endpoint uses global `AuditInterceptor` already, which means every hit to `/dashboard/audit` writes its own `audit_log` row — intentional; dashboard use is itself audited.

### Phase 3.2b Delivery — Conv-9 solo (2026-04-25)
**Scope:** per-artifact RBAC (Python `workflows/acl.py` as single source of truth, NestJS reads via `/acl/artifacts`), global `AuditInterceptor` writing one row per role-gated HTTP request, TypeORM `bids` migration closing the Phase 1 in-memory Map gap. No external deps, $0 cost. Conv-9 solo.

**New files (ai-service):**
- `src/ai-service/workflows/acl.py` — ACL map (14 artifacts × 7 roles) + `has_access()` + `visible_artifacts()` + `acl_as_json()`. Admin is a wildcard.
- `src/ai-service/tests/test_acl.py` — 10 pytest cases; opts out of conftest Temporal imports via local no-op fixture overrides so it runs on a bare Python without `temporalio`.

**Modified (ai-service):**
- `src/ai-service/workflows/router.py` — NEW `GET /workflows/bid/acl/artifacts` + `get_bid_state` now reads `x-user-roles` header and scrubs non-visible BidState fields to `None` (or `[]` for `reviews`). Empty/missing header keeps the old behaviour (trusts internal callers).

**New files (api-gateway):**
- `src/acl/acl.service.ts` + `acl.controller.ts` + `acl.module.ts` — proxies `/acl/artifacts` with a baked-in `FALLBACK_ARTIFACT_ACL` (kept in sync with Python map) so gateway still enforces RBAC if ai-service boot-fetch fails. `assertVisible(roles, key)` throws 403.
- `src/audit/audit-log.entity.ts` + `audit.service.ts` + `audit.interceptor.ts` + `audit.module.ts` — global `AuditInterceptor` registered via `APP_INTERCEPTOR` that fires on routes with `@Roles(...)` metadata. `AuditService.record()` is fire-and-forget — DB failures are logged but never break the request.
- `src/database/database.module.ts` + `datasource.ts` + `migrations/1714000000001-init-bids-and-audit-log.ts` — TypeORM wiring. `POSTGRES_URL` env drives the prod `pg` connection; `migrationsRun: true` on boot.
- `src/workflows/artifact-keys.ts` — extracted `ARTIFACT_KEYS` into a leaf module to break the `AclService ↔ WorkflowsController` circular import (AclService needed the list for `assertVisible`; controller re-exports for DTO consumers).
- `test/acl.service.spec.ts` — 7 specs (fallback map, refresh success, refresh error swallowing, onModuleInit safety, admin wildcard, unknown key, blank-role filtering).
- `test/audit.service.spec.ts` — 3 specs using sqlite in-memory (single row, sequential rows, DB failure swallowing).
- `test/audit.interceptor.spec.ts` — 5 specs (skip @Public routes, 200 on success, HTTP status on error, 500 for plain Error, anonymous fallback).
- `test/bids.service.persistence.spec.ts` — 9 specs against `better-sqlite3` in-memory (create + defaults + ordering + attachWorkflow + findByWorkflowId + update + remove + Redis publish failure swallow).
- `test/rbac-matrix.spec.ts` — **98 parameterised cases** (7 roles × 14 artifacts) + 7 guardrails (unique keys, fallback coverage, pricing commercial-only, bid_card universal, unknown-key rejection, role-union merge, empty-role deny).

**Modified (api-gateway):**
- `package.json` — added `typeorm@^0.3.20`, `@nestjs/typeorm@^10.0.2`, `pg@^8.13.0`, `@types/pg`, `better-sqlite3@^11.3.0` (dev). Plan called for `testcontainers` but Docker isn't available for Jest on this host, so sqlite in-memory was the pragmatic swap — same TypeORM API shape, 10× faster.
- `src/app.module.ts` — wires `DatabaseModule`, `AuditModule`, `AclModule`.
- `src/bids/bid.entity.ts` — `@Entity('bids')` + column mappings; `simple-json` for `technologyKeywords` so it round-trips across pg + sqlite.
- `src/bids/bids.service.ts` — swapped in-memory `Map<id, Bid>` for `Repository<Bid>`; public API now async (`findAll/findOne/update/remove` return Promises). `attachWorkflow` + Redis publish failure handling preserved.
- `src/bids/bids.module.ts` — provides `TypeOrmModule.forFeature([Bid])`.
- `src/bids/bids.controller.ts` — return types now `Promise<Bid[]>` / `Promise<Bid>` / `Promise<void>`.
- `src/workflows/workflows.service.ts` — propagates `x-user-roles` header on every GET/POST to ai-service via new `rolesHeader()` helper. `getStatus/getArtifact/sendReviewSignal` take `roles` param; `requireWorkflowId` is async. New export `X_USER_ROLES_HEADER`.
- `src/workflows/workflows.controller.ts` — `@CurrentUser() user` injected on `status/artifact/review`. `artifact` calls `acl.assertVisible(user.roles, type)` before the upstream hop (defence in depth). `status` now has `@Roles(...all 7...)` so the interceptor records every read.
- `src/workflows/workflows.module.ts` — imports `AclModule` to inject `AclService` into the controller.

**New files (frontend):**
- `lib/api/acl.ts` — `fetchAcl()` + `hasArtifactAccess(acl, roles, key)` pure helper + conservative admin-only `FALLBACK_ACL`.
- `__tests__/rbac-filtering.test.tsx` — 4 render tests (admin sees pricing, BA sees AccessDenied for pricing, bid_card universal, fallback denies non-admin) + 4 helper tests.

**Modified (frontend):**
- `lib/auth/store.ts` — store now holds `acl: AclMap | null` + `setAcl(map)` + `hasArtifactAccess(key)` helper reading `user.roles` + `acl` from the store. `clearAuth` wipes ACL too.
- `components/layout/provider-gate.tsx` — fires `fetchAcl()` once per authed session + stores via `setAcl`. Failures are logged; the store falls back to the admin-only map so non-admin users see placeholders rather than leaked data.
- `components/workflow/state-detail.tsx` — new `NODE_KIND_TO_ARTIFACT` map; `ArtifactPanel` first consults `useAuthStore((s) => s.hasArtifactAccess)` and renders `<AccessDenied artifactKey=... role="alert" aria-label="access-denied" />` when the caller's role is excluded.
- `vitest.setup.ts` — global `beforeEach` seeds an admin session + full ACL map so every existing panel test still renders. Tests that exercise RBAC filtering override in their own `beforeEach`.

**Contract tables:**

| Phase 3.2b contract | Shape | Owner |
|---|---|---|
| `GET /acl/artifacts` (NestJS) | `{ [ArtifactKey]: string[] }` | AclController → proxies AclService |
| `GET /workflows/bid/acl/artifacts` (ai-service) | `{ [ArtifactKey]: string[] }` | Python `acl.acl_as_json()` |
| `x-user-roles` header | comma-separated role list (e.g. `ba,qc`) | NestJS → ai-service every call |
| `audit_log` row | `id, timestamp, user_sub, username, roles, action, resource_type, resource_id, status_code, metadata` | AuditService |
| ACL wildcard | `admin` always resolves True | Python + TS twin implementations |

**Test matrix at delivery:**
- ai-service pytest: **10 ACL cases green** (local `python3`, no temporalio). Remaining ~108 cases carry over to Docker regression (jinja2/temporalio/anthropic/langgraph not on host — consistent with Phase 3.5 / 3.1 carry-forwards).
- api-gateway jest e2e: **161 passed across 10 suites** — 47 pre-existing + 9 persistence + 3 audit.service + 5 audit.interceptor + 7 acl.service + 98 RBAC matrix + 7 matrix guardrails + 2 new workflows.controller (header forward + 403 gate). `npm run build` clean.
- frontend vitest: **73 passed across 13 suites** — 69 pre-existing + 4 rbac-filtering render + 4 hasArtifactAccess helper. `tsc --noEmit` clean. `next build` succeeds.
- `docker compose config` parses.

**Plan → delivery deviations:**
- Plan called for `testcontainers` ^10 to run Postgres in Jest. Host doesn't expose Docker to non-root, so swapped to `better-sqlite3` in-memory — same TypeORM Repository surface, no migration exercise in unit tests. Migrations are exercised only when the NestJS app boots against Postgres (dev/prod).
- Plan called for `CreateDateColumn(timestamptz)` on `audit_log.timestamp`. SQLite doesn't support tz, so entity uses `varchar` with `ISO-8601` strings + the migration declares `timestamp varchar NOT NULL DEFAULT (now()::text)` on Postgres. Same conceptual shape; loses microsecond precision vs `timestamptz` — acceptable for audit fidelity (rows land milliseconds apart at most).
- Plan had a separate `migrations/1700000000001-audit-log-init.ts` + `1700000000002-bids-table.ts`. Merged into one `1714000000001-init-bids-and-audit-log.ts` — they ship together and never need independent down-migrations.
- Plan said `src/.env.example` gains `DATABASE_URL=...`. File in a denied directory; the api-gateway compose service already has `POSTGRES_URL` set → runtime already works. Env.example update carried to next conv with write access.

**Carry-forward (needs Docker, not solved on this host):**
- Live migration run + `SELECT * FROM audit_log` after a real RBAC-gated request — mechanical once Docker is up. Runbook in plan.
- Full `poetry run pytest` on ai-service — depends on Temporal/LangGraph/Anthropic/Jinja2.
- `pytest -m integration` — needs `ANTHROPIC_API_KEY`.
- Browser smoke of the `<AccessDenied>` placeholder for a non-admin Keycloak user.

**Known gotchas introduced this conv:**
- `AclService` constructor uses `@Optional() @Inject(HttpService)` + `@Optional() @Inject(ConfigService)` so RBAC matrix specs can construct it with `new AclService(null, null)` without NestJS DI. Regular DI (in app bootstrap + spec `useValue`) still works.
- Workflows.controller + AclService had a circular import via `ARTIFACT_KEYS`. Extracted to `workflows/artifact-keys.ts`. Re-exported from `workflows.controller.ts` for backwards-compat of `workflows/artifacts.py`-adjacent imports.

### Phase 3.2a Live Smoke — Conv-8b solo (2026-04-23, A+B+C green, D/E/F deferred)
**Outcome:** Phase A (bring-up) + Phase B (PKCE/audience auth path) + Phase C (Bid-M end-to-end via stub LLM) all green. Phase D (real LLM) + E (Langfuse) + F (`pytest -m integration`) deferred — `ANTHROPIC_API_KEY` not yet provided. **3 of 4 deferred-smoke carry-forwards closed:** 3.2a auth (PKCE token + audience mapper), 2.5 streaming (12 `state_completed` events on Redis), 3.1 Jinja proposal (7 sections + 5/5 consistency). Still open: 2.2 (real LLM agents), 3.5 (Langfuse trace).

**Real bug caught + fixed (would have 401'd every browser PKCE login in production):**
- Realm JSON has `attributes.frontendUrl: "http://localhost:8080"` → Keycloak forces token `iss` claim to the public URL **regardless of caller** (browser OR backchannel).
- `JwtStrategy` was checking `iss` against `KEYCLOAK_ISSUER=http://keycloak:8080/realms/bidding` (internal Docker hostname) AND using the same value to build the JWKS URI.
- Result: every valid token returned 401. Browser users would have hit this on day one.
- **Fix:** split into two env vars in `src/api-gateway/src/auth/jwt.strategy.ts`:
  - `KEYCLOAK_PUBLIC_ISSUER` — used as `passport-jwt`'s `issuer:` option (defaults to `KEYCLOAK_ISSUER` for single-host dev).
  - `KEYCLOAK_JWKS_URI` — used for `jwks-rsa`'s URL fetch (defaults to `${KEYCLOAK_ISSUER}/protocol/openid-connect/certs`).
- `src/docker-compose.yml` api-gateway service now sets `KEYCLOAK_PUBLIC_ISSUER=http://localhost:8080/realms/bidding` and `KEYCLOAK_JWKS_URI=http://keycloak:8080/realms/bidding/protocol/openid-connect/certs`. `KEYCLOAK_ISSUER` is kept as the single-source default for both.

**Auth path verified (after the fix):** `aud=bidding-api` ✅, valid token → `200 []` ✅, missing token → `401` ✅, garbage token → `401` ✅. Audience mapper from realm JSON works as designed.

**Workflow path verified:** NEW → S11_DONE in ~10 s. All 12 `state_completed` events fired in correct order S0→S11 + 1 `approval_needed` at S9. Stub-LLM artifacts populated for all 8 keys (ba_draft, sa_draft, domain_notes, convergence, hld, wbs, pricing, proposal_package). `executive_summary: "Stub BA summary for Smoke Test Bank. Derived from 0 requirement atom(s)."` (expected — no key). `/trace-url` → `404` (LANGFUSE_WEB_URL unset, expected).

**Jinja proposal verified:** 7 sections, 180–1930 chars body, 5/5 consistency checks pass: `ba_coverage`, `wbs_matches_pricing`, `client_name_consistent`, `rendered_all_sections`, `terminology_aligned`. NO fallback to 5-section stub.

**Smoke harness deviations from the plan (record so Conv-8c knows):**
- Tested PKCE programmatically via temporary `directAccessGrantsEnabled=true` on `bidding-frontend` (since browser PKCE redirect handler can't be driven from a CLI). Reverted to `false` after smoke. The `lib/auth/pkce.ts` + `/auth/callback/page.tsx` browser path is still only verified by the 65 vitest specs at delivery time — manual browser smoke recommended in Conv-8c.
- `bidadmin` password reset to `Test1234!` via Admin API (override seed `ChangeMe!`); `requiredActions` cleared. Persists in `keycloak_data` volume across `docker compose down` (only wiped by `down -v`).

**Browser smoke follow-up (2nd bug + 1 race fix caught live):**
- **CORS on direct Keycloak token POST:** browsers blocked the fetch from `http://localhost:3001` → `http://localhost:8080/.../token` intermittently (preflight-cache + extensions + WARP + mixed-origin policies all conspire in dev). Server-side CORS config on the realm was correct — this was a client-side / browser-env problem. **Fix:** added a same-origin Next.js API route `app/api/auth/token/route.ts` that proxies the POST to Keycloak over the internal Docker network (`KEYCLOAK_INTERNAL_URL=http://keycloak:8080`). `token-exchange.ts` now posts to `/api/auth/token` — no cross-origin, no preflight, no CORS. Works in any browser/profile.
- **Callback cleanup race:** `if (cancelled) return;` was BEFORE `setAuth(...)`. If React re-rendered the callback page for any reason during the `await exchangeCodeForToken(...)` (strict-mode double-mount, searchParams identity change, dev HMR), the cleanup ran `cancelled=true` and the successfully-purchased token was silently discarded. The auth code is one-shot, so the user then saw "PKCE session not initialised" on retry. **Fix:** moved `setAuth(...)` BEFORE the cancelled guard (zustand store is global, safe to set post-unmount); only the `router.replace(...)` navigation still guards on cancelled.
- Vitest full suite: **65/65 green** after the fix. `next build` succeeds.

**Known gaps still carried forward:**
- Phase D (real LLM) — needs `ANTHROPIC_API_KEY`. ~$0.05–0.10 cost.
- Phase E (Langfuse) — needs `--profile observability` + keys generated post-init. Closes 3.5 smoke.
- Phase F (`pytest -m integration`) — needs key + bind-mount; final regression net.
- `src/.env.example` edit — still permission-denied on this host. The 6 `KEYCLOAK_*` vars + the new `KEYCLOAK_PUBLIC_ISSUER` + `KEYCLOAK_JWKS_URI` need to be appended manually in Conv-8c or 9.
- Silent token refresh + logout UI — still Phase 3.2b work.

### Phase 3.2a Delivery Summary (2026-04-18, Conv-8 solo — code only, live-LLM smoke deferred)
**Scope:** Keycloak realm `bidding` provisioned via `--import-realm`, retire demo-mode in favour of real PKCE + `/auth/callback`, hard-code audience `bidding-api` in the NestJS JWT strategy. The "pair task" half that required Docker + ANTHROPIC_API_KEY (live-LLM smoke) is carried forward.

**New files (infra):**
- `src/keycloak/bidding-realm.json` — realm with 7 roles (admin, bid_manager, ba, sa, qc, domain_expert, solution_lead) + 2 clients (`bidding-api` bearer-only, `bidding-frontend` public PKCE-S256) + audience mapper on the frontend client that injects `bidding-api` into every access token. Seed user `bidadmin / ChangeMe!` with `temporary: true`.
- `src/keycloak/README.md` — runbook for first-login, adding users, re-exporting the realm, and the known gotchas (audience mapper, `##` separator on post-logout URIs, temporary-password quirk).

**Modified (infra):**
- `src/docker-compose.yml` — Keycloak `command: ["start-dev", "--import-realm", "--health-enabled=true"]` + new volume mount `./keycloak:/opt/keycloak/data/import:ro`.

**Modified (api-gateway):**
- `src/auth/jwt.strategy.ts` — `EXPECTED_AUDIENCE = 'bidding-api'` constant + belt-and-braces `matchesAudience` guard inside `validate()` in addition to passport-jwt's own aud check. No longer reads `KEYCLOAK_CLIENT_ID` (hard-coded per D12). Throws `UnauthorizedException` on mismatch.
- `test/auth/jwt.strategy.spec.ts` — NEW. 7 tests: valid payload → AuthenticatedUser; role fallback; username fallback; aud string accepted; aud array accepted; aud string rejected; aud array without bidding-api rejected; missing aud rejected.

**New files (frontend):**
- `lib/auth/pkce.ts` — `generateCodeVerifier`, `computeCodeChallenge` (SHA-256 + base64url), `generateState`, `base64urlEncode`. WebCrypto-only — throws when `crypto.subtle` unavailable.
- `lib/auth/token-exchange.ts` — `exchangeCodeForToken` + `refreshAccessToken` POSTing to the Keycloak token endpoint. Parses access-token claims to reconstruct `AuthUser`. Fetch mockable via `fetchImpl` kwarg for tests.
- `app/auth/callback/page.tsx` — OIDC redirect handler: reads `?code` + `?state`, consumes sessionStorage verifier, exchanges for tokens, stores in `useAuthStore`, redirects to returnTo or `/dashboard`. Renders a friendly error on state mismatch / OAuth error.
- `__tests__/pkce.test.ts` — 5 tests including the RFC 7636 Appendix B vector (`dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk` → `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`).
- `__tests__/keycloak-url.test.ts` — 6 tests covering `buildAuthUrl` / `consumePkceState` / `buildLogoutUrl` + config defaults.
- `__tests__/auth-callback.test.tsx` — 4 tests (happy path, returnTo, state mismatch, OAuth error response).

**Modified (frontend):**
- `lib/auth/keycloak-url.ts` — rewritten from Phase 1 stub to full PKCE flow: `buildAuthUrl` persists verifier + state + optional returnTo into sessionStorage; `consumePkceState` pulls them back out (one-shot, wipes on both success + failure); `buildLogoutUrl` emits the end-session URL; `decodeJwt` kept for the `?devToken=` CI path. Default client id flipped to `bidding-frontend` (was `bidding-web`).
- `lib/auth/store.ts` — `setAuth` now takes optional `{ refreshToken, expiresAt }`; new fields persisted in sessionStorage; `clearAuth` wipes them too.
- `app/login/page.tsx` — demo-mode button retired. Primary CTA now redirects through `buildAuthUrl`. `?devToken=<jwt>` URL param is the only non-Keycloak entry path (auto-runs on mount; no UI).

**Modified (docs):**
- `docs/architecture/SYSTEM_ARCHITECTURE.md` — frontend Auth section rewritten to reflect the PKCE flow + realm provisioning.

**NOT changed (by design):**
- `src/.env.example` — file is in a denied directory from this conversation's perspective; dev env vars below must be added manually. Keep existing `KEYCLOAK_ISSUER`, add/verify `NEXT_PUBLIC_KEYCLOAK_URL=http://localhost:8080`, `NEXT_PUBLIC_KEYCLOAK_REALM=bidding`, `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=bidding-frontend`.

**Contract tables:**

| Phase 3.2a env var | Default | Scope | Notes |
|---|---|---|---|
| `KEYCLOAK_ADMIN` | `admin` | Keycloak container | superuser bootstrap |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Keycloak container | **change before sharing the host** |
| `KEYCLOAK_ISSUER` | `http://keycloak:8080/realms/bidding` | api-gateway | JWKS source for passport-jwt |
| `NEXT_PUBLIC_KEYCLOAK_URL` | `http://localhost:8080` | frontend | browser-facing Keycloak origin |
| `NEXT_PUBLIC_KEYCLOAK_REALM` | `bidding` | frontend | realm path segment |
| `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID` | `bidding-frontend` | frontend | public PKCE client id |

**Tests at delivery — ACTUALLY RAN (after `fix(phase-3.2a-stability)` commit):**
- ai-service: **125 passed**, 1 integration deselected (pytest via local venv).
- api-gateway: **29 passed** across 5 suites (includes the new `test/auth/jwt.strategy.spec.ts`).
- frontend: **65 passed** across 12 suites; `tsc --noEmit` clean; `next build` succeeds.
- `docker compose config` parses clean with the new `./keycloak` mount + `--import-realm` flag.
- `jq . bidding-realm.json` validates.

**Real bugs caught + fixed during the run** (would have blocked live smoke):
1. `BidProfile.M` in Phase 3.1 fixtures — `BidProfile` is a `Literal`, not an Enum → replaced with string constants `PROFILE_S/M/L/XL` (19 pytest failures → green).
2. `<Button asChild>` in the Phase 3.5 `LangfuseLinkButton` — project's Button stub does not support Radix Slot → replaced with a plain `<a>` + `buttonVariants` classes (tsc error).
3. `next build` aborted on `/login` + `/auth/callback` — `useSearchParams` must be wrapped in `<Suspense>` → split each page into outer Suspense boundary + inner implementation.
4. Callback page re-invoked the effect on any router/searchParams identity change (or React 18 strict-mode double-invoke) and hit an already-consumed PKCE session → added `useRef` guard so the side-effect body runs exactly once.
5. Auth-callback test used unstable `useRouter()` / `useSearchParams()` mocks → stable `ROUTER` + `SEARCH_PARAMS` constants.
6. Proposal-panel test used ambiguous `getByText('Cover Page')` — markdown body also renders it as `<h1>` → scoped lookup to `<summary>` elements.

Also: installed `react-markdown` into the frontend lockfile, added a Node webcrypto polyfill in `vitest.setup.ts` for jsdom environments that hide `globalThis.crypto`.

**Deferred smoke (Phase D in plan) — CARRY-FORWARD to Conv-8b:**
1. `cp src/.env.example src/.env` + set `ANTHROPIC_API_KEY=sk-ant-...`.
2. `cd src && docker compose up -d --build` — all 10 services healthy (Langfuse NOT started by default).
3. Verify realm imported: `curl http://localhost:8080/realms/bidding/.well-known/openid-configuration | jq .issuer`.
4. Log into Keycloak Admin UI (admin / admin) → realm `bidding` → change `bidadmin` password (forced).
5. Log into frontend at `http://localhost:3001` as `bidadmin` → triggers PKCE → `/auth/callback` → dashboard.
6. Create Bid-M → Trigger workflow → approve triage → approve review.
7. Simultaneously `docker exec bid-redis redis-cli PSUBSCRIBE 'bid.events.channel.*'` — expect `state_completed` + `agent_token` events.
8. `GET /bids/:id/workflow/artifacts/ba_draft` — `executive_summary` must NOT start with `"Stub BA summary"`.
9. Open Langfuse (optional, needs `--profile observability`) at `http://localhost:3002/trace/<bid_id>`. Expect 1 trace / 3 spans / 9 generations.
10. `GET /bids/:id/workflow/artifacts/proposal_package` — 7 sections with real template output (not 5-section stub).
11. `pytest -m integration -v` via bind-mount as the final gate.

Rebuild BOTH `ai-service` + `ai-worker` images between steps 1 and 2 — see `memory/project_docker_image_split.md`.

**Known gaps carried to Phase 3.2b / later:**
- `src/.env.example` edit — still permission-denied on this host. Add the 6 new `KEYCLOAK_*` + `NEXT_PUBLIC_KEYCLOAK_*` rows on the next conv with write access.
- Silent token refresh before `expiresAt` — not wired yet. Access tokens expire in 15 min; app will 401 after that. Phase 3.2b (or a small follow-up) wires a silent-refresh timer in `useAuthStore`.
- Logout button/UI — `buildLogoutUrl` exists but no UI consumer yet. Trivial — top-bar user menu in Phase 3.2b.
- Keycloak HA + persistent realm secrets — Phase 3.6 Helm chart.
- Live-LLM smoke runbook above — block of Conv-8b when infra available.

### Phase 3.1 Delivery Summary (2026-04-18, Conv-7 solo)
**Scope:** replace the hand-written stub sections in `activities/assembly.py` with Jinja2-rendered proposal output. 7 sections per `ProposalPackage`; per-section null-guards (Bid-S skips HLD + pricing → "Not applicable"); `RendererError` triggers stub-fallback so a bid never fails on templating. Frontend `ProposalPanel` now renders full markdown via `react-markdown` with per-section `<details>` accordion. No LLM — $0.

**New files (ai-service):**
- `assembly/__init__.py` — package exports.
- `assembly/renderer.py` — `render_package` + `render_section` + `_build_env` with `StrictUndefined`, autoescape off, `currency` + `date` Jinja filters, `PROPOSAL_SECTIONS` ordered tuple (template_stem, heading, sourced_from).
- `assembly/consistency.py` — 5 checks (`ba_coverage`, `wbs_matches_pricing`, `client_name_consistent`, `rendered_all_sections`, `terminology_aligned`) + helpers.
- `templates/proposal/_macros.md.j2` — shared `section_header` / `subheader` / `bullet_list` / `section_or_na` / `kv_line` macros.
- `templates/proposal/{00-cover, 01-executive-summary, 02-business-requirements, 03-technical-approach, 04-wbs-estimation, 05-pricing-commercials, 06-terms-appendix}.md.j2` — 7 section templates with `{% if %}` null-guards.
- `tests/fixtures/bid_states.py` — 3 seed `AssemblyInput` factories (`full_bid_m`, `minimal_bid_s`, `edge_bid`).
- `tests/test_proposal_renderer.py` — 6 tests (cover renders client, full 7-section render, Bid-S null HLD+pricing, edge zero-subtotal, StrictUndefined catches typos, all sections non-empty).
- `tests/test_proposal_consistency.py` — 10 tests (one per check + positive/negative cases + Bid-S null-pricing short-circuit).

**Modified (ai-service):**
- `pyproject.toml` — add `jinja2 ^3.1.0`.
- `workflows/artifacts.py` — widen `AssemblyInput` with optional `bid_card`/`triage`/`scoping`/`convergence`/`reviews`/`generated_at` (first three typed `Any` to dodge the `models.py → artifacts.py` import cycle). Import `Any` from typing. DTO backward-compat — every new field has a default.
- `workflows/bid_workflow.py::_run_s8_assembly` — pass the widened context to `AssemblyInput` (bid_card/triage/scoping/convergence/reviews + `workflow.now()` for `generated_at`).
- `activities/assembly.py` — complete rewrite: calls `render_package` first, falls back to the pre-3.1 5-section stub on `RendererError`. Stub-fallback flips `consistency_checks["rendered_all_sections"] = False` + sets `template_error = True` so the UI can surface the degradation.
- `tests/test_activities.py` — 3 new assembly tests (full-template render, template-error → stub shape, Bid-S null-pricing).

**New files (frontend):**
- `__tests__/proposal-panel.test.tsx` — 4 tests (empty placeholder, 3 sections + titles visible, first section `open` by default, consistency_checks list rendered).

**Modified (frontend):**
- `package.json` — add `react-markdown ^9.0.0`.
- `components/workflow/state-detail.tsx::ProposalPanel` — accordion via `<details>` / `<summary>`; first section expanded by default; body rendered with `<ReactMarkdown>`; `data-testid="proposal-section"` on each entry for the test suite. Existing consistency block kept.

**Temporal data-converter quirk (flagged for future devs):**
- Workflow-side `AssemblyInput(bid_card=BidCard(...), triage=TriageDecision(...), scoping=ScopingResult(...))` is serialized with `Any` fields → reconstructs on the activity side as **plain dicts with ISO-string datetimes**. Templates use Jinja's attribute-then-dict fallback so `bid.client_name` still resolves. The `| date` filter now parses ISO strings (see `assembly/renderer.py::_filter_date`).

**NO CHANGES (by design):**
- `api-gateway` — `proposal_package` artifact proxied verbatim; shape unchanged; only content richer.
- `workflows/artifacts.py::ProposalPackage` + `ProposalSection` DTO — unchanged.

**Infra (ai-service Dockerfile):**
- No change needed — `COPY . .` already picks up the new `templates/` directory; `.dockerignore` does not exclude it. Tests still bind-mount per the existing `project_docker_image_split.md` pattern.

**Contract tables:**

| Proposal section | Template file | sourced_from |
|---|---|---|
| Cover Page | `00-cover.md.j2` | `bid_card` |
| Executive Summary | `01-executive-summary.md.j2` | `ba_draft` |
| Business Requirements | `02-business-requirements.md.j2` | `ba_draft` |
| Technical Approach | `03-technical-approach.md.j2` | `sa_draft` |
| WBS + Estimation | `04-wbs-estimation.md.j2` | `wbs` |
| Pricing + Commercials | `05-pricing-commercials.md.j2` | `pricing` |
| Terms + Appendix | `06-terms-appendix.md.j2` | `domain_notes` |

| consistency check | when `False` |
|---|---|
| `ba_coverage` | A MUST functional requirement's ID + title missing from all rendered bodies |
| `wbs_matches_pricing` | `sum(lines) != subtotal` OR `subtotal * (1 + margin/100) != total` (±0.01) |
| `client_name_consistent` | Client name absent from Cover OR Executive Summary body |
| `rendered_all_sections` | Fewer than 7 sections (stub-fallback path sets this `False`) |
| `terminology_aligned` | Same section uses rival terms (customer vs client, solution vs system) |

**Tests at delivery (expected, NOT executed — Docker + Poetry still unavailable on this host):**
- ai-service: **+19 tests** (6 renderer + 10 consistency + 3 activity). Pre-existing 105 + 19 = **124 target**.
- api-gateway: **0 new** — unchanged.
- frontend: **+4 tests** (proposal panel). Pre-existing 43 + 4 = **47 target**.

**Live smoke:** NOT yet run — deferred alongside Phase 3.5's live smoke to Conv-8 with Docker access.

**Runbook (for Conv-8):**
```bash
# 1. Confirm local test suites green
cd src/ai-service && poetry install && poetry run pytest -v
cd ../api-gateway && npm install && npm run test:e2e
cd ../frontend && npm install && npx vitest run && npx tsc --noEmit && npm run build

# 2. Docker rebuild (templates are baked in via COPY .)
cd src && docker compose up -d --build ai-service ai-worker
docker compose restart ai-worker

# 3. Smoke — any Bid-M workflow reaching S8
BID_ID=...
curl -s http://localhost:3000/bids/$BID_ID/workflow/artifacts/proposal_package \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.sections[] | {heading, head: .body_markdown[:120]}'
# Expect 7 entries starting with headings above. Bid-S should show
# "Not applicable" on Pricing + Technical Approach sections.
```

**Known gaps carried to Phase 3.1b / later:**
- DOCX export (`python-docx` + markdown→DOCX) — 3.1b.
- PDF export (`weasyprint` + system libs) — 3.1b.
- Client-branded template overrides — 3.3.
- LLM re-phrasing pass (Sonnet polish after templating) — 3.4 may reuse.
- `ba_coverage` check uses substring match — false-positive risk when titles are generic; deferred to 3.3 when the audit dashboard can flag noisy checks.
- `@tailwindcss/typography` plugin NOT installed — `prose` classes on the panel no-op for now. Add in 3.1b or 3.3 if designers want styled markdown.

### Phase 3.5 Delivery Summary (2026-04-18, Conv-6 solo)
**Scope:** self-hosted Langfuse tracing wrapped around `ClaudeClient.generate` + `generate_stream`; activity-level spans bound via `_CURRENT_LLM_SPAN` ContextVar so BA/SA/Domain LLM calls land under one `trace_id=str(bid_id)`. Deterministic-first: `LANGFUSE_SECRET_KEY` unset → no-op tracer, zero HTTP traffic, Langfuse container NOT started.

**New files (ai-service):**
- `config/langfuse.py` — `LangfuseSettings` (env prefix `LANGFUSE_`) + `get_langfuse_settings` lru_cache.
- `tools/langfuse_client.py` — `LangfuseTracer` (lazy SDK import), `_RealSpan` / `_RealGeneration` + `_NoopSpan` / `_NoopGeneration` siblings, `_CURRENT_LLM_SPAN` ContextVar, `span_context` asynccontextmanager, `get_tracer` factory. Noop-by-default: `tracer.enabled = bool(secret_key)`.
- `tests/test_langfuse_client.py` — 5 tests (disabled→noop, span_context propagation, aclose idempotent, enabled-path SDK calls, SDK errors degrade).
- `tests/test_claude_client_tracing.py` — 4 tests (generate creates generation when span bound, generate_stream captures aggregate, no-op without span, error path still closes generation).

**Modified (ai-service):**
- `pyproject.toml` — add `langfuse ^2.59.0`.
- `tools/claude_client.py` — constructor accepts `tracer` kwarg (defaults to `get_tracer()`). `generate` + `generate_stream` open + close a Langfuse generation around the Anthropic call via `_start_generation` helper. New optional `trace_id` + `node_name` kwargs. `_NOOP_GEN` fallback when no span bound.
- `agents/_streaming.py::call_llm` — passes `node_name=` through to both `generate` / `generate_stream`.
- `activities/ba_analysis.py`, `sa_analysis.py`, `domain_mining.py` — in the real-LLM branch, open `tracer.start_span(trace_id=str(req.bid_id), name="{agent}_analysis", metadata={attempt,agent})`, nest `async with langfuse_span_context(span), stream_context(publisher)`, end span + `tracer.aclose()` in `finally`. Stub branch unchanged.
- `tests/conftest.py` — new autouse fixture `_disable_langfuse_by_default` scrubs `LANGFUSE_*` env vars + clears settings cache for non-integration tests (mirror of `_force_llm_fallback_by_default`).

**New files (api-gateway):**
- `src/bids/langfuse-link.service.ts` — `LangfuseLinkService.getTraceUrl(bidId)` returns `{url: "${LANGFUSE_WEB_URL}/trace/${bidId}"}`, throws `NotFoundException` when env unset.
- `test/langfuse-link.service.spec.ts` — 3 tests (url returned, trailing slash stripped, 404 when env unset).

**Modified (api-gateway):**
- `src/bids/bids.controller.ts` — `GET /bids/:id/trace-url` endpoint gated `@Roles('admin','bid_manager')`. Injects `LangfuseLinkService`.
- `src/bids/bids.module.ts` — provide `LangfuseLinkService`.
- `test/bids.controller.spec.ts` — add `LangfuseLinkService` mock to providers; 2 new specs (success + 404).

**New files (frontend):**
- `components/bids/langfuse-link-button.tsx` — opens Langfuse trace in new tab. Hidden unless user has `admin`/`bid_manager` role AND gateway returns a URL (silently hidden on 404).
- `__tests__/langfuse-link-button.test.tsx` — 3 tests (admin sees link, viewer sees nothing, 404 hides).

**Modified (frontend):**
- `lib/api/bids.ts` — `getBidTraceUrl(id)` helper.
- `app/(authed)/bids/[id]/page.tsx` — mount `<LangfuseLinkButton>` next to `wf: ...` chip when `b.workflowId` exists.

**Modified (infra):**
- `src/docker-compose.yml` — new services `langfuse-db-init` (one-shot postgres client that `CREATE DATABASE langfuse_db` if not exists) + `langfuse-server` (image `langfuse/langfuse:2.59`, reuses existing postgres, port 3002:3000), both behind `profiles: ["observability"]`. ai-service + ai-worker get `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` / `LANGFUSE_RELEASE` env passthrough (default empty → noop). api-gateway gets `LANGFUSE_WEB_URL`.
- `docker compose config` validates clean. Default `docker compose up -d` still starts 10 services (Langfuse skipped).
- `.env.example` — NOT modified (permission denied on file); runbook documents `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` / `LANGFUSE_WEB_URL` / `LANGFUSE_RELEASE` + `LANGFUSE_NEXTAUTH_SECRET` / `LANGFUSE_SALT` keys instead. Carry-forward to Phase 3.6 K8s manifests.

**Contract tables:**

| Env var | Default | Required when | Notes |
|---|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | (unset) | observability profile | from Langfuse UI |
| `LANGFUSE_SECRET_KEY` | (unset) | observability profile | **gates the no-op wrapper** |
| `LANGFUSE_HOST` | `http://langfuse-server:3000` | observability profile | ai-service side |
| `LANGFUSE_WEB_URL` | (unset) | api-gateway only | browser-facing; 404 on /trace-url when unset |
| `LANGFUSE_RELEASE` | `phase-3.5` | optional | tagged on every trace |
| `LANGFUSE_NEXTAUTH_SECRET` | placeholder | observability profile | Langfuse server auth |
| `LANGFUSE_SALT` | placeholder | observability profile | Langfuse server |

| Trace shape | |
|---|---|
| `trace(id=str(bid_id))` | implicit — activities use `trace_id=str(bid_id)` convention |
| `span(name="{agent}_analysis", metadata={attempt,agent})` | one per BA/SA/Domain activity attempt |
| `generation(name="<node>", model, input, output, usage)` | one per LLM call (Haiku extract/classify/tag + Sonnet synth + Sonnet critique) |

**REST:** `GET /bids/:id/trace-url` → `{url: "..."}` (200) OR 404 when `LANGFUSE_WEB_URL` unset. Roles: admin + bid_manager.

**Tests at delivery:**
- ai-service: expected **+8 tests** (5 langfuse_client + 3 claude_client_tracing + 1 error-path). NOT yet executed — Docker daemon + Poetry env unavailable in this conv (mirror of Phase 2.5 + 2.4 deferral). Test files were written to mirror existing patterns (autouse fixtures scrub env, mock Langfuse SDK via `MagicMock`). Re-run at start of Conv-7 before any new code.
- api-gateway: expected **+5 tests** (3 langfuse-link service + 2 controller specs). Same deferral.
- frontend: expected **+3 tests** (link button visibility matrix). Same deferral.

**Live smoke:** NOT yet run in this conversation — Docker daemon not accessible. Runbook carried forward below.

**Runbook:**
```bash
# Default dev (no Langfuse) — unchanged
cd src && docker compose up -d --build
# 10 services healthy, Langfuse NOT started.

# Opt into observability
docker compose --profile observability up -d langfuse-db-init langfuse-server
# Wait for langfuse-server healthy (~30s), then:
open http://localhost:3002    # create admin user + project, copy public+secret keys
cat >> .env <<EOF
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://langfuse-server:3000
LANGFUSE_WEB_URL=http://localhost:3002
LANGFUSE_NEXTAUTH_SECRET=<openssl rand -hex 32>
LANGFUSE_SALT=<openssl rand -hex 32>
EOF
# Rebuild BOTH ai-service + ai-worker (Docker image split — see project_docker_image_split.md)
docker compose up -d --build ai-service ai-worker api-gateway
docker compose restart ai-worker

# Set ANTHROPIC_API_KEY too, trigger a workflow, open http://localhost:3002/trace/<bid_id>
# Expect: 1 trace per bid, 3 spans (BA/SA/Domain) per run, 3 generations per span (9 total for Bid-M).
```

**Known gaps carried to Phase 3.6+ / future convs:**
- Live smoke (Langfuse + real LLM) not yet run — deferred to next conv with Docker access.
- `.env.example` not modified — document the 6 new vars at the top of the file on the next conv that has write access.
- Langfuse admin bootstrap still manual — Phase 3.6 Helm chart should automate via init container (D10 carry-forward).
- OTLP bridge for non-Python services deferred to Phase 3.7.
- Langfuse Prompts SDK (prompt version tracking) deferred to Phase 3.3.
- PII redaction deferred to Phase 3.2 RBAC scope.

### Phase 2.5 Delivery Summary (2026-04-18, Conv-5 solo)
**Scope:** real-time agent token streaming + per-phase `state_completed` events + frontend `AgentStreamPanel`. All on the existing Redis pub/sub + socket.io fanout — zero new infra. Deterministic-first: zero `agent_token` publishes when `ANTHROPIC_API_KEY` absent; `state_completed` always fires.

**New files (ai-service):**
- `agents/stream_publisher.py` — `TokenPublisher` with throttled Redis PUBLISH (150 ms / 200 chars), `stream_context` asynccontextmanager, `_CURRENT_PUBLISHER` ContextVar. Best-effort (swallows Redis errors).
- `agents/_streaming.py` — `call_llm(client, *, node_name, ...)` helper: dispatches to `generate_stream` when publisher bound, else `generate`. Single-source for BA/SA/Domain node calls.
- `activities/state_transition.py` — `state_transition_activity` best-effort notify; payload `{type:"state_completed", state, profile, artifact_keys, occurred_at}`.
- `tests/test_stream_publisher.py` (7 tests), `tests/test_state_transition_activity.py` (3 tests), `tests/test_ba_agent_streaming.py` (4 tests — BA + SA + Domain symmetric coverage + BA fallthrough), `tests/test_workflow_stream_events.py` (2 tests).

**Modified (ai-service):**
- `tools/claude_client.py` — new `generate_stream(..., on_token)` method using Anthropic `messages.stream`. Existing `generate` untouched. `on_token` errors logged + swallowed.
- `agents/ba_agent.py`, `agents/sa_agent.py`, `agents/domain_agent.py` — each swapped its 3 `client.generate(...)` call sites (Haiku extract/classify/tag + Sonnet synthesize + Sonnet critique) for `call_llm(..., node_name=...)`. Retrieve node (Qdrant) NOT streamed.
- `activities/ba_analysis.py`, `activities/sa_analysis.py`, `activities/domain_mining.py` — inside the `if get_claude_settings().api_key` branch, instantiate `TokenPublisher(bid_id, agent, attempt=activity.info().attempt)` + `async with stream_context(pub): ...` + `aclose` in `finally`. Stub-fallback branch unchanged (no publisher, no tokens).
- `workflows/bid_workflow.py` — new `_PHASE_ARTIFACT_KEYS` declarative map, `_notify_state_transition(phase, keys)` helper (best-effort, 10s timeout, 1 attempt), `_complete_phase(phase)` wrapper (snapshot → notify order for read-your-writes), `run()` swaps every `await self._snapshot_workspace(X)` for `await self._complete_phase(X)`. Removed duplicate terminal `S11_DONE` snapshot (previously fired twice).
- `worker.py` — registers `state_transition_activity`.
- `tests/conftest.py` — new autouse fixture `_stub_redis_publish` monkeypatches `aioredis.from_url` across `activities.notify`, `activities.state_transition`, `agents.stream_publisher` so unit tests observe publishes without a real Redis. Exposes `_RedisCapture.events_of_type(t)` helper.
- `tests/test_workflow.py::_ALL_ACTIVITIES` — adds `state_transition_activity`.
- `tests/test_claude_client.py` — 3 new tests (stream forwards deltas, no-callback drains, on_token error swallowed).

**New files (frontend):**
- `components/workflow/agent-stream-panel.tsx` — collapsible panel (BA/SA/Domain label + node label + done/streaming badge + typewriter pre block). Renders idle state when stream is null.
- `__tests__/use-bid-events-stream.test.ts` (9 tests: 5 `applyToken` pure-function + 4 hook scenarios including 150 ms throttle, state_transitions buffering, bid-id switch reset, backwards-compat with `approval_needed`).
- `__tests__/agent-stream-panel.test.tsx` (3 tests).

**Modified (frontend):**
- `lib/ws/use-bid-events.ts` — extended `BidEventState` with `agentStreams: Record<AgentName, AgentStreamState | null>` + `stateTransitions: StateCompletedEvent[]`. Ref-based buffer + 150 ms throttled setState (`FLUSH_INTERVAL_MS`). Pure `applyToken` function handles attempt-dedup + node-reset + out-of-order seq drop. Transitions capped at 50. Buffer resets on bid-id change.
- `components/workflow/state-detail.tsx` — props extend with `agentStreams`; when `currentState === 'S3'` and selected is S3a/b/c, renders `<AgentStreamPanel>` above the existing artifact panel.
- `app/(authed)/bids/[id]/page.tsx` — pipes `agentStreams` from `useBidEvents` into `<StateDetail>`.

**NO CHANGES (by design, per D1):**
- `api-gateway/src/gateway/events.gateway.ts` — existing `relayToRoom` already fans out any Redis payload verbatim; new event types ride the same channel + same `bid.event` WS message.
- `api-gateway/src/redis/redis.service.ts` — no new methods needed.

**Contract tables (Redis payloads on `bid.events.channel.{bid_id}`):**

| type | fields |
|---|---|
| `agent_token` (new) | `agent ∈ {ba,sa,domain}`, `node`, `attempt`, `seq`, `text_delta`, `done` |
| `state_completed` (new) | `state` (e.g. `"S4_DONE"`), `profile`, `artifact_keys: string[]`, `occurred_at` ISO8601 |
| `approval_needed` (unchanged, Phase 2.4) | `state`, `workflow_id`, `round`, `reviewer_index`, `reviewer_count`, `profile` |

**Tests at delivery:** **97/97 pytest** (78 pre-existing + 7 publisher + 3 state_transition + 2 workflow events + 3 claude streaming + 4 agent streaming: BA+SA+Domain symmetric + fallthrough); 1 integration test correctly deselected. **17/17 Jest** (NestJS untouched). **41/41 vitest** (29 pre + 9 hook streaming + 3 panel). `tsc --noEmit` clean; `next build` succeeds.

**Live smoke:** NOT yet run in this conversation — Docker daemon not accessible. Runbook (carry forward to next conv):
```bash
# Rebuild BOTH images (per project_docker_image_split.md)
cd src && docker compose up -d --build ai-service ai-worker
docker compose restart ai-worker

# Without key — expect state_completed events, zero agent_token
curl -X POST http://localhost:8001/workflows/bid/start-from-card -H 'Content-Type: application/json' -d '{...}' | jq .workflow_id
# approve triage + review signals, watch `docker exec bid-redis redis-cli PSUBSCRIBE 'bid.events.channel.*'`
# Should see ~12 state_completed payloads (Bid-M); 0 agent_token.

# With key — expect both
# add ANTHROPIC_API_KEY to src/.env → docker compose up --build -d ai-service ai-worker
# Same start + signal flow; expect bursts of agent_token events during S3.
# Run the gated integration test:
docker run --rm --network bid-framework_default -v "$PWD/ai-service/tests:/app/tests:ro" \
  -e ANTHROPIC_API_KEY=... bid-framework-ai-service sh -c "pip install -q pytest pytest-asyncio && pytest -m integration -v"
```

**Known gaps carried to Phase 3:**
- SSE endpoint parity (deferred — socket.io already carries both streams; add SSE only if a non-browser consumer needs it).
- Token persistence via Redis XADD + MAXLEN (for late subscribers) — Phase 3.3 audit dashboard will want historical token streams.
- Langfuse trace around `generate_stream` — Phase 3.5.
- Per-tenant isolation before re-surfacing `kb-vault/bids/` in RAG — Phase 3 (multi-tenant tag contract).
- Frontend panel doesn't yet render `stateTransitions` as a live activity feed (buffer is populated but no UI consumer) — trivial to add in Phase 3 audit dashboard.

### Phase 2.6 + 2.4 Delivery Summary (2026-04-18, Conv-4 pair)
**Scope:** declarative profile pipeline (2.6) + real S9 human review gate with signal + loop-back + multi-round cap + WebSocket notification (2.4).

**Phase 2.6 (commit `8e96c17`):**
- `workflows/bid_workflow.py` — `_PROFILE_PIPELINE: dict[BidProfile, tuple[str,...]]` + `_STATE_DISPATCH_MAP`; `run()` now iterates the active profile's pipeline.
- Bid-S = `(S0, S1, S2, S3, S4, S6, S8, S9, S10, S11)` — skips S3c (via scoping re-route, pre-existing), S5 Solution Design, and S7 Commercial. Bid-M/L/XL = full 12-state pipeline; XL logs `XL_PARITY_PENDING` (S3d/S3e deferred to Phase 3).
- `S9_BLOCKED` added as terminal in `WorkflowState` literal + frontend `state-palette.ts` (danger tone) + `workflow-graph.tsx::mainOrderForCompare`.
- `AssemblyInput.hld` / `AssemblyInput.pricing` now `| None`; `assembly.py` null-guards both with Bid-S fallback text. `WBSInput.hld` likewise optional.
- `tests/conftest.py::_compress_gate_timeouts` autouse fixture compresses `HUMAN_GATE_TIMEOUT` / `ACTIVITY_TIMEOUT` / `S3_ACTIVITY_TIMEOUT` / `_S9_TIMEOUT` to 5s for non-integration tests.
- `tests/test_workflow_profile_routing.py` — 4 tests (Bid-S/M/L/XL).

**Phase 2.4 (commit below):**
- `workflows/models.py` — new `HumanReviewSignal`, `LoopBack` DTOs; `BidState.loop_back_history` field.
- `workflows/bid_workflow.py` — `@workflow.signal("human_review_decision")` handler appends to a FIFO queue (`_review_signals` + `_review_consumed` cursor) so pre-delivered signals aren't dropped by `self._review_signal = None` resets. `_run_s9_review_gate` runs pre-human `review_activity` then iterates per-profile reviewer count (`_S9_REVIEWER_COUNT = {S:1, M:1, L:3, XL:5}`); per-profile timeout (`_S9_TIMEOUT`, 72h / 120h XL). Any REJECT / CHANGES_REQUESTED short-circuits remaining reviewers in the round. 3-round cap terminates at `S9_BLOCKED`. `_route_on_changes_requested` picks earliest target from `_LOOP_BACK_ORDER = ("S2","S5","S6","S8")`, falls forward to nearest pipeline-resident state on Bid-S (e.g. `target=S5` falls forward to S6), clears downstream artifacts via declarative `_ARTIFACT_CLEANUP`.
- `activities/notify.py` (new) — `notify_approval_needed_activity` PUBLISHes `{type:"approval_needed",...}` to `bid.events.channel.<bid_id>` via `redis.asyncio`; wrapped in try/except so workflow never fails on Redis outage.
- `activities/review.py` — renamed to `_pre_human_review_impl` + `review_activity` wrapper; same consistency-check derivation but verdict explicitly tagged `phase-2.4-pre-human`.
- `workflows/router.py` — `POST /workflows/bid/{wf}/review-signal`.
- `api-gateway/src/workflows/review-signal.dto.ts` (new) — class-validator DTO for `verdict / reviewer / reviewerRole / comments / notes`.
- `workflows.service.ts::sendReviewSignal` — camelCase → snake_case transform; 409 CONFLICT if current_state ≠ S9 before forwarding.
- `workflows.controller.ts` — `POST review-signal` gated `@Roles('admin','bid_manager','qc','sa','domain_expert','solution_lead')` (new roles added to `roles.decorator.ts`).
- `frontend/components/bids/review-gate-panel.tsx` (new) — react-hook-form panel mirroring `TriageReviewPanel` shape; repeatable `comments[]` (section / severity / target_state); mounts at `currentState === 'S9'`.
- `frontend/lib/ws/use-bid-events.ts` — adds `approvalNeeded` state from `bid.event.type === 'approval_needed'` payload.
- Bid detail page renders `ReviewGatePanel` at S9 + `S9_BLOCKED` banner.

**New / modified files:**
- ai-service new: `activities/notify.py`, `tests/test_workflow_profile_routing.py`, `tests/test_workflow_review_gate.py`.
- ai-service modified: `workflows/base.py`, `workflows/models.py`, `workflows/artifacts.py`, `workflows/bid_workflow.py`, `workflows/router.py`, `activities/assembly.py`, `activities/review.py`, `worker.py`, `tests/conftest.py`, `tests/test_workflow.py`.
- api-gateway new: `src/workflows/review-signal.dto.ts`.
- api-gateway modified: `src/workflows/workflows.controller.ts`, `src/workflows/workflows.service.ts`, `src/auth/roles.decorator.ts`, `test/workflows.controller.spec.ts`.
- frontend new: `components/bids/review-gate-panel.tsx`, `__tests__/review-gate-panel.test.tsx`.
- frontend modified: `lib/api/types.ts`, `lib/api/bids.ts`, `lib/hooks/use-bids.ts`, `lib/ws/use-bid-events.ts`, `lib/utils/state-palette.ts`, `components/workflow/workflow-graph.tsx`, `app/(authed)/bids/[id]/page.tsx`, `__tests__/state-palette.test.ts`.
- docs: `docs/states/STATE_MACHINE.md` state matrix column flipped to "Status (2.6)" + SKIP (live) on S3c/S5/S7 for Bid-S + S9 row upgraded to "REAL (signal + loop-back)".

**Tests:** 78 pytest (70 + 8 new review-gate) + 4 new profile routing already counted; 17 Jest (14 + 3 new review-signal specs); 29 vitest (27 + 2 new review-gate-panel tests). All green; 1 integration test deselected.

**Live HTTP smoke:** not re-run (needs rebuilt ai-service + ai-worker images to pick up workflow bytecode; see `project_docker_image_split.md`). Recommended runbook: see plan step 31 in memory `project_phase_2_4_2_6_detailed_plan.md`.

### Phase 2.7 Delivery Summary (2026-04-18)
**Scope:** per-bid Obsidian workspace under `kb-vault/bids/{bid_id}/`. `workspace_snapshot_activity` fires after every workflow phase; writes are best-effort (bid completion > vault completeness).

**Design delta:** flat layout (`NN-<phase>.md` + single `09-reviews/` subfolder) instead of 11 nested phase dirs — better Obsidian file-tree UX. `kind: bid_output` frontmatter tags every file. Vault NOT re-ingested into Qdrant — Phase 3 adds multi-tenant isolation before enabling RAG over prior bids.

**New files:** `src/ai-service/kb_writer/{__init__,models,templates,bid_workspace}.py`; `activities/bid_workspace.py`; `tests/test_kb_writer.py` (5 tests); `tests/test_bid_workspace.py` (4 tests, tmp_path).

**Modified:** `workflows/bid_workflow.py` (11 snapshot call sites + `_snapshot_workspace` helper); `worker.py` (register workspace activity); `tests/test_workflow.py` (add to `_ALL_ACTIVITIES`); `tests/conftest.py` (`_sandbox_kb_vault` autouse → `KB_VAULT_PATH` per-test tmp).

**Tests:** 66 pytest (57 + 9 new), 14 Jest, 25 vitest — all green.

### Phase 2.3 Delivery Summary (2026-04-17)
**Scope:** upload PDF/DOCX RFP → ParsedRFP → suggested BidCard pre-fill. No LLM, no new Docker service.

**Design delta:** swapped Unstructured.io (1.5GB RAM container) for pypdf + python-docx (~1MB deps, pure Python). `parsers/` abstraction keeps the option open to plug Unstructured.io back in for OCR/complex-tables in Phase 3.

**New files:** `src/ai-service/parsers/{__init__,models,pypdf_adapter,docx_adapter,rfp_extractor}.py`; `tests/test_parsers.py` (13 tests); `src/api-gateway/src/parsers/{parsers.module,controller,service}.ts`; `test/parsers.controller.spec.ts` (3 tests); `src/frontend/lib/api/parsers.ts`; `src/frontend/components/bids/{rfp-upload,new-bid-shell}.tsx`.

**Modified:** `src/ai-service/pyproject.toml` (pypdf + python-docx + python-frontmatter deps); `workflows/router.py` (POST /workflows/bid/parse-rfp); `src/api-gateway/src/app.module.ts` (mount ParsersModule); `src/frontend/components/bids/create-bid-form.tsx` (accepts initialValues + resetToken props); `app/(authed)/bids/new/page.tsx` (uses NewBidShell).

**Tests:** 57 pytest (44 + 13 new), 14/14 Jest (11 + 3 new), 25/25 vitest, tsc + next build clean.

### Live after Phase 2.1 (what a dev can run today)
- `cd src && docker compose up --build -d` → **10** services healthy (~60–120s cold start)
- Frontend at `http://localhost:3001` → Demo-mode login renders dashboard + ReactFlow DAG with artifact panels for all 11 states
- Temporal UI at `http://localhost:8088`
- ai-service direct API at `http://localhost:8001/docs` (Swagger) — `/workflows/bid/*` endpoints walk the full S0→S11_DONE pipeline
- NestJS api-gateway at `http://localhost:3000` — new `GET /bids/:id/workflow/artifacts/:type` endpoint (JWT-gated, 14 artifact keys)
- Keycloak admin at `http://localhost:8080` (admin/admin) — realm `bidding` not yet provisioned (Phase 1.x), so authenticated flows need a pasted JWT or realm import

### Phase 2.2 Delivery Summary (2026-04-17, deterministic-first path)
**Scope:** full code path for real LangGraph-backed S3a/b/c + heuristic S4 convergence. Shipped without `ANTHROPIC_API_KEY` via a per-activity fallback gate — each real activity wrapper checks `get_claude_settings().api_key` and falls back to the Phase 2.1 deterministic stub when absent. 44/44 pytest pass (33 pre-existing + 11 new).

**Files added:**
- `src/ai-service/agents/prompts/sa_agent.py` + `agents/sa_agent.py` — Haiku classify + Sonnet synth/critique; LangGraph 4-node graph mirrors BA pattern (retrieve → classify → synth → critique → loop-on-low-confidence)
- `src/ai-service/agents/prompts/domain_agent.py` + `agents/domain_agent.py` — same shape, Haiku tags + Sonnet compliance + practices + glossary
- `src/ai-service/activities/sa_analysis.py` + `activities/domain_mining.py` — Temporal wrappers with heartbeats + stub-fallback gate
- `src/ai-service/tests/test_sa_agent.py` (3), `tests/test_domain_agent.py` (3), `tests/test_convergence.py` (5), `tests/test_workflow_integration.py` (1, gated)

**Files modified:**
- `src/ai-service/agents/models.py` — deleted `BARequirements`; BA agent now consumes shared `StreamInput` DTO (Q1 unification)
- `src/ai-service/agents/ba_agent.py` — input type rename only
- `src/ai-service/activities/ba_analysis.py` — input rename + same stub-fallback gate as SA/Domain
- `src/ai-service/activities/convergence.py` — 3 heuristic conflict rules (API-layer mismatch, compliance-gap, NFR-field-presence); readiness = 0.40·ba + 0.35·sa + 0.25·domain with gate at 0.80; `build_convergence_report` pure function extracted for unit tests
- `src/ai-service/workflows/bid_workflow.py::_run_s3_streams` — real activity refs; S3 timeout bumped 5min→10min + 2min heartbeat
- `src/ai-service/worker.py` — real activities registered; stubs kept in codebase (callable via fallback) but out of registry
- `src/ai-service/tests/test_workflow.py` — registers real activities in `_ALL_ACTIVITIES`; tests stay LLM-free because conftest autouse scrubs the key
- `src/ai-service/tests/conftest.py` — new autouse fixture `_force_llm_fallback_by_default` scrubs `ANTHROPIC_API_KEY` + clears `get_claude_settings` cache for every non-integration test
- `src/ai-service/pyproject.toml` — `addopts = "-m 'not integration'"` + `integration` marker registered
- `docs/phases/PHASE_2_PLAN.md` — Task 2.2 DELIVERED block
- `src/ai-service/CLAUDE.md` — stub-vs-real wording updated

**Test results:**
- ai-service: **44/44 pytest pass** (33 pre-existing + 3 SA + 3 Domain + 5 Convergence); 1 integration test correctly deselected via `-m 'not integration'`
- api-gateway: untouched, still 11/11 Jest
- frontend: untouched, still 24/24 vitest
- Live HTTP smoke: **not yet re-run** — Phase 2.1 behaviour unchanged because every test env + the existing running worker both take the stub-fallback path. Rebuild `ai-service` + `ai-worker` images + set `ANTHROPIC_API_KEY` before smoke-testing real agents.

### Phase 2.1 Delivery Summary (2026-04-17)
**Scope:** Deterministic 11-state DAG end-to-end with all S3..S11 artifacts stubbed. No LLM calls — unblocks shippable milestone without `ANTHROPIC_API_KEY`.

**Files added:**
- `src/ai-service/workflows/base.py` — shared primitives (RequirementAtom, BidProfile, WorkflowState) — broke circular import
- `src/ai-service/workflows/artifacts.py` — 20+ Pydantic DTOs for S3b..S11 artifacts + activity inputs
- `src/ai-service/activities/stream_stubs.py` — `ba_analysis_stub_activity`, `sa_analysis_stub_activity`, `domain_mining_stub_activity`
- `src/ai-service/activities/{convergence,solution_design,wbs,commercial,assembly,review,submission,retrospective}.py` — 8 downstream stubs
- `src/api-gateway/src/workflows/workflows.controller.ts` — new `@Get('artifacts/:type')` handler; `ARTIFACT_KEYS` exported
- `src/frontend/components/workflow/state-detail.tsx` — rewrote to render all 14 artifact types (BA/SA/Domain/Convergence/HLD/WBS/Pricing/Proposal/Reviews/Submission/Retrospective) with compact summaries

**Files modified:**
- `src/ai-service/workflows/models.py` — `WorkflowState` now includes `S11_DONE`; `BidState` has 11 new artifact fields
- `src/ai-service/workflows/bid_workflow.py` — rewrote `run()` as S0→S11_DONE; S3 parallel via `asyncio.gather`; per-state `_run_sN_*` helpers; state machine extended
- `src/ai-service/worker.py` — registers 11 new activities (does NOT register `ba_analysis_activity` — stays dormant until Phase 2.2)
- `src/ai-service/tests/test_workflow.py` — approved path now expects `S11_DONE`; new test `test_workflow_full_pipeline_populates_all_artifacts` asserts every artifact field present
- `src/ai-service/agents/models.py` — `RequirementAtom` now imported from `workflows.base` (cycle break)
- `src/api-gateway/src/workflows/workflows.service.ts` — `getArtifact(bidId, key)` proxies to status + extracts field
- `src/api-gateway/test/workflows.controller.spec.ts` — 3 new specs (ok, unknown-key 400, missing-field 404)
- `src/frontend/lib/api/types.ts` — 14 new Phase 2.1 artifact interfaces mirror Python payload (snake_case)
- `src/frontend/lib/api/bids.ts` — `getWorkflowArtifact<T>(id, type)` helper
- `src/frontend/lib/utils/state-palette.ts` — `S11_DONE` added; tone = `done`
- `src/frontend/app/(authed)/bids/[id]/page.tsx` — `inferSelected` routes `S11_DONE` to `S11`

**Test results:**
- ai-service: **33/33 pytest pass** (32 from Phase 1 + 1 new full-pipeline E2E)
- api-gateway: **11/11 Jest specs pass** (8 existing + 3 new artifact endpoint specs)
- frontend: **24/24 vitest pass**, `tsc --noEmit` clean, `next build` succeeds
- Live HTTP: workflow started via `POST /workflows/bid/start-from-card` + approve signal reaches `S11_DONE` with all 11 artifacts populated (WBS total_effort_md=205, pricing.total ≈ $246k, submission confirmation SUB-xxxxxxxx)

### Phase 1 Hardening Pass (2026-04-17 PM)
Cold-start on a fresh host revealed 7 defects in the original Phase 1 delivery — all fixed and verified:

| # | File | Defect | Fix |
|---|---|---|---|
| 1 | `ai-service/pyproject.toml` | `python = "^3.12"` resolves `>=3.12,<4.0`, conflicts with `fastembed` (<3.13) → build fail | Narrowed to `python = ">=3.12,<3.13"` |
| 2 | `src/docker-compose.yml` temporal healthcheck | Used `sh /dev/tcp/...` — auto-setup image's `sh` lacks `/dev/tcp`, probe always fails | Switched to `tctl --address $(hostname):7233 cluster health \| grep -q SERVING` (127.0.0.1 wrong — Temporal binds to container IP) |
| 3 | `src/docker-compose.yml` keycloak healthcheck | Probed mgmt port 9000, but KC 24 doesn't expose separate mgmt port (25+ only) | Probe `/health/ready` on port 8080 |
| 4 | `src/frontend/Dockerfile` | Missing `ARG NEXT_PUBLIC_*` → Next.js inlines fallback `http://localhost:3001` → dashboard calls frontend instead of gateway → client-side crash | Added build ARGs + ENV; compose passes `args:` block |
| 5 | `src/docker-compose.yml` | No `ai-worker` service → Temporal task queue has no consumer → workflows accepted but never processed | Added `ai-worker` service running `python worker.py` reusing ai-service image |
| 6 | `ai-service/config/temporal.py` + `worker.py` | Default JSON converter loses pydantic type on `handle.query` round-trip (Pydantic v2 warning had been firing) | Wired `temporalio.contrib.pydantic.pydantic_data_converter` on both worker + client |
| 7 | `ai-service/agents/ba_agent.py` | Graph always loops when confidence < 0.5, even with empty KB — crashes BA tests and wastes LLM calls on RAG outage | `_route_after_critique` short-circuits to END when `retrieved` is empty (degraded mode) |
| 8 | `src/docker-compose.yml` ai-worker | Inherited ai-service image's HEALTHCHECK (probe HTTP :8001) but `worker.py` does not listen → container always reports `unhealthy` | `healthcheck: {disable: true}`; rely on `restart: unless-stopped` for liveness |

Also added: `./kb-vault` bind-mounted into ai-service + ai-worker at `/kb-vault` with `KB_VAULT_PATH=/kb-vault`, so `python -m ingestion` works out of the box.

### Phase 1 Verification Runbook (run these to confirm a clean state)
```bash
# 1. Cold start
cd src && docker compose up -d --build           # expect 10 services healthy
docker compose ps -a                              # all "Up … (healthy)"

# 2. Seed data
docker exec bid-ai-service python -m rag.seed                    # 61 chunks / 9 files
docker exec bid-ai-service python -m ingestion                   # 21 notes / 111 edges

# 3. Workflow E2E (no LLM required — stub deterministic S0→S1→S2)
curl -s -X POST http://localhost:8001/workflows/bid/start-from-card \
  -H 'Content-Type: application/json' \
  -d '{"client_name":"Verify","industry":"Banking","region":"SEA","deadline":"2026-12-31T00:00:00Z","scope_summary":"verify","technology_keywords":["go"],"estimated_profile":"M","requirements_raw":["x"]}'
# → {"workflow_id":"bid-<uuid>",...}
# Send approve signal:
curl -s -X POST http://localhost:8001/workflows/bid/<id>/triage-signal \
  -H 'Content-Type: application/json' -d '{"approved":true,"reviewer":"verify"}'
# Query:
curl -s http://localhost:8001/workflows/bid/<id> | jq .current_state  # → "S2_DONE"

# 4. Tests — all green after the hardening pass
# ai-service (32 tests) — tests/ is dockerignored; run via temp container with bind-mount
docker run --rm --network bid-framework_default \
  -v "$PWD/ai-service/tests:/app/tests:ro" \
  -e QDRANT_URL=http://qdrant:6333 -e TEMPORAL_HOST=temporal:7233 -e REDIS_URL=redis://redis:6379 \
  bid-framework-ai-service sh -c "pip install -q pytest pytest-asyncio && pytest -v"
# api-gateway (8 tests) — use test:e2e not default test (rootDir miss)
cd api-gateway && npm run test:e2e
# frontend (24 tests + typecheck + build)
cd ../frontend && npx vitest run && npx tsc --noEmit && npm run build
```

### Documentation refreshed (2026-04-17)
- `CURRENT_STATE.md` (this file) — Phase 1 complete, Next Action = Phase 2.1
- `docs/phases/PHASE_1_PLAN.md` — each task has a "DELIVERED" block + Phase 1 Delivered Summary (waves, test counts, contracts, known gaps)
- `docs/states/STATE_MACHINE.md` — state matrix annotated with Phase 1 impl status; implementation pointers table added
- `docs/architecture/SYSTEM_ARCHITECTURE.md` — "Phase 1 Implementation Map" appended (layer → files/containers + cross-service contracts)
- Sub-repo CLAUDE.md added for vibe coding with cwd inside any service:
  - `src/ai-service/CLAUDE.md`
  - `src/api-gateway/CLAUDE.md`
  - `src/frontend/CLAUDE.md`
  - `src/kb-vault/CLAUDE.md`

---

## Phase 1: Core Foundation (Weeks 1-4)

| # | Task | Status | Notes |
|---|---|---|---|
| 1.1 | Setup project structure + Docker Compose | DONE | 9 services, healthchecks wired, `docker compose config` clean |
| 1.2 | Temporal workflow: S0 + S1 + S2 | DONE | `bid_workflow.py` + intake/triage/scoping activities + FastAPI router + `/start-from-card` for UI-entered bids |
| 1.3 | 1 LangGraph agent (BA Agent) PoC | DONE | 4-node graph (retrieve→Haiku extract→Sonnet synth→Sonnet critique), prompt caching, activity wrapper ready. NOT yet registered in `worker.py` — wired in Phase 2.2 |
| 1.4 | Basic RAG: Qdrant + embedding pipeline | DONE | fastembed (bge-small 384d) + BM25 sparse → Qdrant RRF fusion + Cohere rerank fallback; 9 seed docs; idempotent UUID5 upserts |
| 1.5 | Obsidian KB vault + ingestion service | DONE | 20 notes / 5 doc_types / 81+ links; `IngestionService` with watchdog+polling fallback, hash cache, graph snapshot |
| 1.6 | NestJS API gateway + Keycloak auth | DONE | Bids CRUD + workflow proxy + WS gateway; JWKS-backed JWT guard + roles guard; realm provisioning deferred |
| 1.7 | Minimal Next.js frontend | DONE | App Router, zustand + TanStack Query + ReactFlow + socket.io; demo-mode login; tsc/vitest/build/lint green |

## Phase 2: Full Pipeline (Weeks 5-8)

| # | Task | Status | Notes |
|---|---|---|---|
| 2.1 | Complete 11-state DAG in Temporal | DONE | 11 deterministic stubs wired via asyncio.gather for S3; workflow reaches S11_DONE end-to-end |
| 2.2 | Parallel agent execution (S3a, S3b, S3c) | DONE (deterministic-first) | Real BA/SA/Domain LangGraph agents + heuristic S4 convergence shipped. Each activity falls back to its stub until `ANTHROPIC_API_KEY` is set. 44/44 pytest pass; 1 integration test deselected |
| 2.3 | Document parsing pipeline | DONE (pypdf MVP) | PDF + DOCX → ParsedRFP + BidCard suggestion. pypdf + python-docx (no Unstructured.io container); gateway proxy + frontend drop-zone; 13 new pytest + 3 new Jest |
| 2.7 | Bid workspace in Obsidian | DONE | Flat `kb-vault/bids/{bid_id}/NN-*.md` layout; `workspace_snapshot_activity` after each phase; 15 render funcs with `kind: bid_output` frontmatter; best-effort (never blocks bid). Re-ingestion deferred to Phase 3 |
| 2.4 | Human approval flow (Temporal signals) | DONE | Real S9 gate: `human_review_decision` signal, sequential multi-reviewer, earliest-target loop-back with artifact cleanup, 3-round cap → S9_BLOCKED; `notify_approval_needed_activity` WS broadcast |
| 2.5 | Real-time updates (SSE + WebSocket) | DONE | `TokenPublisher` (throttle 150 ms / 200 chars) + `stream_context` ContextVar → agents route through `ClaudeClient.generate_stream`; `state_transition_activity` after each phase. Frontend `AgentStreamPanel` + extended `useBidEvents`. 97 pytest, 41 vitest. |
| 2.6 | Bid Profile routing (S/M/L/XL) | DONE | `_PROFILE_PIPELINE` matrix; Bid-S skips S5/S7; assembly null-guards; XL logs parity-pending |

## Phase 3: Production Ready (Weeks 9-12)

| # | Task | Status | Notes |
|---|---|---|---|
| 3.1 | Document generation (proposal templates) | DONE (Jinja-backed) | 7 markdown sections + 5-check consistency + stub-fallback on `RendererError`; frontend accordion via `react-markdown`. DOCX/PDF export deferred to 3.1b |
| 3.2a | Keycloak realm + PKCE frontend + audience check | DONE (code) · smoke deferred | `bidding-realm.json` imported by Keycloak; demo-mode retired; JwtStrategy hard-codes `bidding-api` audience. Live-LLM smoke waits for Docker + ANTHROPIC_API_KEY |
| 3.2b | Full RBAC per role (per-artifact ACL + audit + bids migration) | NOT STARTED | |
| 3.3 | Audit dashboard | NOT STARTED | |
| 3.4 | Retrospective module (S11) | NOT STARTED | |
| 3.5 | LLM observability (Langfuse) | DONE (deterministic-first) | LangfuseTracer noop wrapper + SDK path; activity spans + ClaudeClient generations; /bids/:id/trace-url gateway; Langfuse-link frontend button; docker-compose `profiles:["observability"]`. Live smoke + `.env.example` deferred |
| 3.6 | Kubernetes migration | NOT STARTED | |
| 3.7 | Performance optimization + load test | NOT STARTED | |

---

## Decisions Made

| Decision | Choice | Date | Reason |
|---|---|---|---|
| Orchestration | Temporal.io + LangGraph | 2026-04-17 | Temporal for durability, LangGraph for AI agents |
| LLM Strategy | Full Claude API (Sonnet + Haiku) | 2026-04-17 | Quality first, optimize cost via tiered routing + caching |
| Vector DB | Qdrant (primary) + pgvector (convenience) | 2026-04-17 | Hybrid search, self-hosted, enterprise filtering |
| API Gateway | NestJS (TypeScript) | 2026-04-17 | Auth, RBAC, WebSocket |
| AI Services | Python FastAPI + Temporal workers | 2026-04-17 | AI/ML ecosystem, LangGraph |
| Frontend | Next.js App Router + shadcn/ui + ReactFlow | 2026-04-17 | SSR, realtime, DAG visualization |
| Knowledge Workspace | Obsidian (Git sync) | 2026-04-17 | Free, markdown-based, [[links]] = knowledge graph |
| Doc Parsing | Unstructured.io (self-hosted) | 2026-04-17 | Best PDF/DOCX quality, open-source |
| Auth | Keycloak (self-hosted) | 2026-04-17 | Enterprise identity, SSO, free |
| Observability | Langfuse (self-hosted) | 2026-04-17 | Open-source thay LangSmith, $0 |
| Phase 1 Infra | Docker Compose on VPS | 2026-04-17 | K8s chưa cần, migrate Phase 3 |

## Open Questions

- [ ] Client nào dùng thử pilot?
- [ ] Data sovereignty requirements cụ thể?
- [ ] Existing KB data ở đâu? Format gì?
- [ ] Team size cho Phase 1 development?

## Known Gaps Carried Into Phase 3

Audited + pruned 2026-04-18 after Phase 2 closure. Stale entries removed:
~~`ba_analysis_activity` not registered~~ (registered since Phase 2.2);
~~Triage shape mismatch~~ (closed as part of Phase 2 audit — frontend `Triage`
now matches Python `TriageDecision`).

- **Keycloak realm `bidding` not provisioned** — `docker-compose.yml` runs `start-dev` without `--import-realm`; add `bidding-realm.json` and `--import-realm` flag before wiring real auth end-to-end. Phase 3.2 owns.
- **Api-gateway Jest `rootDir=src` only discovers `src/**/*.spec.ts`** — run `npm run test:e2e` (or move specs under `src/`) to include `test/*.spec.ts`. Unchanged convention; documented.
- **Postgres persistence for bids uses an in-memory Map** in `bids.service.ts` — swap for TypeORM/Prisma in Phase 3. `bidding_db` is empty (0 tables) — no migration yet.
- **CORS defaults to `*`** when `CORS_ORIGIN` unset — tighten before any shared-environment deploy.
- **ai-service `Dockerfile` `.dockerignore` excludes `tests/`** — pytest must run via bind-mount (`docker run --rm -v "$PWD/tests:/app/tests:ro" ...`) rather than `docker exec`. Consider a separate `Dockerfile.test` target in Phase 3.
- **`ANTHROPIC_API_KEY` not wired from `.env` by default** — `src/.env` not created by compose. Copy `.env.example` → `.env` and set the key before running any LLM-dependent flow (real BA/SA/Domain agents, Cohere rerank, Phase 2.5 token streams). S0–S11 run on deterministic stubs + fallback gate, need no key.
- **`ai-worker` uses a separate Docker image tag** (`bid-framework-ai-worker`) — when iterating on workflow/activity code, rebuild BOTH `ai-service` AND `ai-worker` images, then force-recreate the worker container. Runbook: see `memory/project_docker_image_split.md`. Was the #1 debug blocker in 2.1; recurred in 2.4/2.5 deliveries.
- **`kb-vault/bids/` NOT re-ingested into Qdrant** (Phase 2.7 carry-forward) — multi-tenant isolation required before prior-bid content surfaces to new-bid RAG. Phase 3 owns.
- **Live-LLM smoke for Phase 2.2 + 2.5 not yet run** — stub path is default; set `ANTHROPIC_API_KEY`, rebuild both images, run `pytest -m integration -v`. `ba_draft.executive_summary` no longer starts with `"Stub BA summary"` when live.
