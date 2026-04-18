# Phase 3: Production Ready (Weeks 9-12)

## Goal
Document generation, full RBAC, audit, observability, production deployment.

---

## Task 3.1: Document Generation
- Proposal templates (Jinja2 + python-docx)
- Template library: cover page, executive summary, technical sections, WBS, pricing
- AI content + template structure -> final PDF/DOCX
- Consistency checker (numbers, terminology, tone)

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

## Task 3.5: LLM Observability (Langfuse)
- Self-hosted Langfuse deployment (`profiles: ["observability"]` — opt-in)
- Trace every LLM call (prompt, response, cost, latency) via `ClaudeClient.generate` + `generate_stream` wrapper
- Trace hierarchy: `trace(bid_id)` > `span(agent_analysis)` > `generation(node)`
- Cost dashboard per bid / per state / per agent — Langfuse UI native (uses SDK-provided model pricing)
- Quality scoring per agent — deferred to Phase 3.3 (audit dashboard)

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
