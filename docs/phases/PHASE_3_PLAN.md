# Phase 3: Production Ready (Weeks 9-12)

## Goal
Document generation, full RBAC, audit, observability, production deployment.

---

## Task 3.1: Document Generation — DELIVERED (markdown, 3.1b deferred)
- Jinja2 markdown templates (7 sections) + `assembly.renderer.render_package` replacing the pre-3.1 hand-written stub.
- Template library: `00-cover`, `01-executive-summary`, `02-business-requirements`, `03-technical-approach`, `04-wbs-estimation`, `05-pricing-commercials`, `06-terms-appendix` + shared `_macros.md.j2`. All null-guarded so Bid-S (no HLD, no pricing) still produces 7 sections with a "Not applicable" placeholder.
- Consistency checker (`assembly.consistency`): `ba_coverage`, `wbs_matches_pricing`, `client_name_consistent`, `rendered_all_sections`, `terminology_aligned`.
- Stub-fallback: any `RendererError` routes to the legacy 5-section stub + flips `consistency_checks.template_error = True` so the review gate can see the degradation.
- Frontend `ProposalPanel` renders each section in a native `<details>` accordion with `react-markdown`.

**Deferred to 3.1b / 3.3:**
- DOCX export (`python-docx` + markdown→DOCX).
- PDF export (`weasyprint`; adds ~150 MB image size).
- Client-branded template overrides (`templates/proposal/overrides/{client_id}/…`).
- LLM re-phrasing polish pass.

**Delivery manifest:** see memory `project_phase_3_1_delivered.md` and `CURRENT_STATE.md`.

## Task 3.2: Full RBAC
- Fine-grained permissions per role per bid
- Row-level security in PostgreSQL
- Stream access control (SA sees tech, BA sees business, etc.)
- Audit log for all permission-gated actions

## Task 3.3: Audit Dashboard
- Temporal Visibility API integration
- Workflow history viewer
- Decision trail (who approved what, when, why)
- LLM cost tracking per bid

## Task 3.4: Retrospective Module (S11)
- Win/loss tracking
- Lessons learned -> auto-update KB
- Actual vs Estimated analysis
- Estimation model refinement

## Task 3.5: LLM Observability (Langfuse) — DELIVERED
- Self-hosted Langfuse deployment (`profiles: ["observability"]` — opt-in) sharing the bidding Postgres with a dedicated `langfuse_db`.
- Every LLM call wrapped in `tools.langfuse_client.LangfuseTracer` — no-op when `LANGFUSE_SECRET_KEY` unset.
- Trace hierarchy `trace_id=str(bid_id) > span({agent}_analysis) > generation(<node>)`.
- `GET /bids/:id/trace-url` (admin + bid_manager) + frontend `LangfuseLinkButton` opens the Langfuse UI in a new tab.
- Cost dashboard per bid / per state / per agent — native Langfuse UI (pricing handled SDK-side).
- Quality scoring per agent — deferred to Phase 3.3 audit dashboard.

**Delivery manifest:** see memory `project_phase_3_5_delivered.md` and `CURRENT_STATE.md`.

**Detailed execution plan:** see memory record `project_phase_3_5_detailed_plan.md`
(12 decisions, 21-step order, $0 cost, ~500 LOC, solo-conv recommendation).
Key design pillars:
- `trace_id = str(bid_id)` convention — deterministic, no workflow-side Langfuse call, preserves Temporal replay safety.
- `_CURRENT_LLM_SPAN` ContextVar mirrors Phase 2.5's `TokenPublisher` pattern so LangGraph nodes stay argless.
- No-op wrapper when `LANGFUSE_SECRET_KEY` absent — tests + stub path unchanged.
- Reuses existing `postgres` service (new DB `langfuse_db`) instead of spinning up a dedicated Postgres.

## Task 3.6: Kubernetes Migration
- Helm charts for all services
- Horizontal pod autoscaling
- Health checks, readiness probes
- Secret management (Vault or K8s secrets)

## Task 3.7: Performance & Load Testing
- Simulate concurrent bids
- Measure agent latency, workflow throughput
- Identify bottlenecks
- Optimize RAG retrieval speed
