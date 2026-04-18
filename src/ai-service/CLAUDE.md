# ai-service (Python) — AI Bidding Framework

> Local CLAUDE.md. Root config lives at `../../CLAUDE.md`. Read that first for project-wide rules. This file adds service-specific context.

## Role
- Python 3.12 / FastAPI app + Temporal workers + LangGraph agents + RAG pipeline + Obsidian ingestion.
- Listens on port `8001`. Temporal worker is a separate entrypoint (`worker.py`) — run alongside the FastAPI app in prod.
- Upstream: NestJS api-gateway calls us at `http://ai-service:8001/workflows/bid/*`.
- Downstream: Qdrant (`qdrant:6333`), Temporal (`temporal:7233`), Redis (`redis:6379`), Postgres (`postgres:5432`), Anthropic API.

## Delivery status (Phase 3.1 — Jinja-backed proposal + Langfuse observability)
- Full 11-state DAG wired end-to-end: S0 Intake → S1 Triage (+human gate) → S2 Scoping → S3a/b/c parallel → S4..S11 → terminal `S11_DONE` (or `S9_BLOCKED` when review gate exhausts rounds).
- S0/S1/S2 use real heuristics. S3a/b/c have three real LangGraph agents (BA/SA/Domain) with per-activity fallback to deterministic stubs (gate: `config.claude.get_claude_settings().api_key`).
- S3 streaming (Phase 2.5): `TokenPublisher` + `generate_stream` → Redis pub/sub → frontend `AgentStreamPanel`; `state_transition_activity` broadcasts phase completions.
- S4 Convergence: heuristic cross-stream conflicts + weighted readiness gate 0.80. Real semantic LLM-compare deferred.
- S5/S7 real stubs; S6 real WBS template.
- **S8 Assembly (Phase 3.1):** seven Jinja-rendered proposal sections via `assembly/renderer.py`. Stub-fallback on `RendererError` so a bid never fails on a template glitch.
- S9 Review gate (Phase 2.4): real signal + loop-back + multi-round cap → `S9_BLOCKED` on exhaustion.
- S2.6 Profile routing: Bid-S skips S5/S7; Bid-M/L full pipeline; XL logs parity-pending.
- **Phase 3.5 Langfuse observability:** `ClaudeClient.generate`/`generate_stream` open a generation under an activity-level span when a span is bound via `tools.langfuse_client.span_context`. No-op when `LANGFUSE_SECRET_KEY` unset.

## Quick commands
```bash
# Install
poetry install

# FastAPI (dev)
poetry run uvicorn main:app --reload --port 8001

# Temporal worker (dev, separate shell)
poetry run python worker.py

# Tests
poetry run pytest                       # all
poetry run pytest tests/test_workflow.py -v

# Lint / format / type
poetry run ruff check .
poetry run black .
poetry run mypy .

# Seed RAG with sample docs (needs Qdrant up)
poetry run python -m rag.seed

# Run ingestion (needs Qdrant up + KB_VAULT_PATH set)
poetry run python -m ingestion --vault ../kb-vault --watch
```

## File tour (Phase 2.1)
```
ai-service/
  main.py                    # FastAPI app + /health; mounts workflows/router.py
  worker.py                  # Temporal worker entrypoint (task queue: bid-workflow-queue)
  pyproject.toml             # Poetry manifest

  config/
    temporal.py              # TemporalSettings + get_temporal_client()
    qdrant.py                # QdrantSettings + AsyncQdrantClient + ensure_collection()
    embeddings.py            # EmbeddingSettings
    claude.py                # ClaudeSettings + HAIKU / SONNET model constants
    ingestion.py             # IngestionSettings (env prefix KB_)

  workflows/
    base.py                  # Shared primitives — RequirementAtom, BidProfile, WorkflowState, utcnow
                             # Sits at the bottom of the dep graph so models + artifacts + agents
                             # can all import it without a circular.
    models.py                # S0-S2 DTOs + BidState (extended w/ 11 Phase 2.1 artifact fields).
                             # Re-exports WorkflowState, RequirementAtom, BidProfile from base.
    artifacts.py             # Phase 2.1 artifact DTOs: SolutionArchitectureDraft, DomainNotes,
                             # ConvergenceReport, HLDDraft, WBSDraft, PricingDraft, ProposalPackage,
                             # ReviewRecord, SubmissionRecord, RetrospectiveDraft + activity
                             # input types (StreamInput, ConvergenceInput, AssemblyInput, …).
    bid_workflow.py          # BidWorkflow @workflow.defn — full 11-state DAG (S0 → S11_DONE).
                             # _run_s3_streams dispatches S3a/b/c in parallel via asyncio.gather.
    router.py                # FastAPI: /start, /start-from-card, /{id}/triage-signal, /{id}

  activities/
    intake.py                # S0: parse raw RFP → BidCard
    triage.py                # S1: calls agents/triage_agent.py::score
    scoping.py               # S2: requirement decomposition + stream assignment
    stream_stubs.py          # S3a/b/c deterministic stubs (Phase 2.1). Each derives its output
                             # from the scoping atoms. Phase 2.2 replaces all three with real LLM
                             # activities.
    ba_analysis.py           # S3a real wrapper: runs agents/ba_agent.py; falls back to
                             # ba_analysis_stub_activity when ANTHROPIC_API_KEY is unset.
    sa_analysis.py           # S3b real wrapper: runs agents/sa_agent.py; same fallback gate.
    domain_mining.py         # S3c real wrapper: runs agents/domain_agent.py; same fallback gate.
    convergence.py           # S4: merges stream outputs, emits heuristic cross-stream conflicts
                             # (API-layer / compliance / NFR) + weighted readiness gate 0.80.
    bid_workspace.py         # workspace_snapshot_activity — best-effort per-phase markdown
                             # write to kb-vault/bids/{bid_id}/. Catches all exceptions so
                             # vault issues never fail the workflow.
    solution_design.py       # S5 stub — HLD skeleton from SA draft + convergence report.
    wbs.py                   # S6 stub — default WBS template, effort biased by BA MUSTs.
    commercial.py            # S7 stub — fixed-price advisory model (blended day rate).
    assembly.py              # S8 Phase 3.1 — calls `assembly.render_package`; falls back to
                             # the legacy 5-section stub on `RendererError` (template safety net).
    review.py                # S9 stub — auto-approves (consistency_checks always pass on stub
                             # packages). Phase 2.4 replaces with real human signal + loop-back.
    submission.py            # S10 stub — cutover checklist + SHA-256 package checksum.
    retrospective.py         # S11 stub — default lessons + KB update queue placeholder.

  agents/
    triage_agent.py          # Stub deterministic scorer (swap-point for LLM)
    ba_agent.py              # LangGraph 4-node: retrieve → extract(Haiku) → synth(Sonnet) → critique(Sonnet)
    sa_agent.py              # LangGraph 4-node: retrieve → classify(Haiku) → synth(Sonnet) → critique(Sonnet)
    domain_agent.py          # LangGraph 4-node: retrieve → tag(Haiku) → synth(Sonnet) → critique(Sonnet)
    models.py                # BA-agent output DTOs (BusinessRequirementsDraft, FunctionalRequirement,
                             # RiskItem, SimilarProject). SA + Domain output DTOs live in workflows/artifacts.py.
                             # Shared input DTO for all 3 streams is StreamInput (also in workflows/artifacts.py).
    prompts/ba_agent.py      # Versioned system prompts for BA graph
    prompts/sa_agent.py      # SA graph system prompts
    prompts/domain_agent.py  # Domain graph system prompts

  assembly/                  # Phase 3.1 — Jinja2 proposal rendering.
    __init__.py              # re-exports render_package + RendererError + PROPOSAL_SECTIONS
    renderer.py              # `render_package(AssemblyInput) -> ProposalPackage`; loads templates
                             # from ../templates/proposal/*.md.j2 with StrictUndefined + currency/date filters.
    consistency.py           # 5 cross-section checks: ba_coverage, wbs_matches_pricing,
                             # client_name_consistent, rendered_all_sections, terminology_aligned.

  templates/proposal/        # Phase 3.1 — 7 .md.j2 section templates + _macros.md.j2.
                             # Packaged into the ai-service image via Dockerfile `COPY . .`.

  tools/
    claude_client.py         # AsyncAnthropic wrapper with cache_control: ephemeral (prompt caching).
                             # Phase 3.5: generate/generate_stream open Langfuse generations when a
                             # span is bound via tools/langfuse_client.span_context.
    langfuse_client.py       # Phase 3.5 — LangfuseTracer with no-op fallback; _CURRENT_LLM_SPAN
                             # ContextVar; span_context asynccontextmanager.
    kb_search.py             # Qdrant search wrapper; degrades to [] on error

  config/
    langfuse.py              # Phase 3.5 — LangfuseSettings (env prefix LANGFUSE_).

  parsers/                   # Phase 2.3 — RFP → ParsedRFP → BidCardSuggestion.
    models.py                # ParsedRFP, Section, TableBlob, BidCardSuggestion, ParseResponse.
    pypdf_adapter.py         # PDF → ParsedRFP (regex heading classifier + ascii-pipe tables).
    docx_adapter.py          # DOCX → ParsedRFP (Word paragraph styles for headings).
    rfp_extractor.py         # Heuristic mapper: industry/region dicts + modal-verb requirements.

  kb_writer/                 # Phase 2.7 — BidState → per-bid Obsidian markdown workspace.
    models.py                # WorkspaceInput (activity arg) + WorkspaceReceipt (return).
    templates.py             # 15 render_* funcs, f-string + textwrap.dedent + frontmatter.
    bid_workspace.py         # ensure_workspace + write_snapshot (atomic file writes).

  rag/
    embeddings.py            # fastembed (bge-small + BM25) providers
    indexer.py               # chunk_markdown + index_documents (UUID5 stable IDs)
    retriever.py             # hybrid_search (RRF fusion) + rerank (Cohere optional)
    seed.py                  # python -m rag.seed
    sample_docs/             # 9 seed markdown files

  ingestion/
    vault_parser.py          # ParsedNote (frontmatter + headings + links + sha256 hash)
    link_extractor.py        # [[wiki-links]] extraction + LinkEdge
    vault_scanner.py         # Async .md walker; skips .obsidian/ .git/
    watcher.py               # watchdog + polling fallback, 500ms debounce
    ingestion_service.py     # initial_index + on_file_change + hash cache
    graph_store.py           # In-memory KnowledgeGraph + JSON snapshot
    __main__.py              # python -m ingestion

  tests/                     # pytest; mirrors src layout
```

## Conventions (reinforces root CLAUDE.md)
- snake_case filenames
- Full type hints on every public function
- Async by default (FastAPI + Temporal activities)
- Pydantic for all I/O — no raw dicts crossing boundaries
- Use `logging.getLogger(__name__)` — never `print`
- One-line docstrings only; no paragraph docs
- Temporal activities must be `@activity.defn`, take ONE Pydantic arg, return a Pydantic model
- Workflow code must be deterministic — use `workflow.now()` (never `datetime.utcnow`), never `uuid4()` / `random` / threads inside `@workflow.run`

## LLM routing (per root CLAUDE.md)
- **Haiku** (`claude-haiku-4-5-20251001`) — extraction, classification, routing
- **Sonnet** (`claude-sonnet-4-6`) — reasoning, synthesis, self-critique
- Prompt caching is MANDATORY on system prompts: `cache_control: {type: "ephemeral"}` via `ClaudeClient.generate(cache_system=True)` (default)

## Known gotchas
- Temporal `auto-setup` takes ~60–90s cold start; worker should retry Temporal connection.
- `temporalio`, `langgraph`, `qdrant-client`, `anthropic` are NOT installed on the dev host; tests that import them will fail on bare `pytest`. Run via Docker or `poetry install` first.
- S3a/b/c use real LangGraph agents wrapped in Temporal activities (`ba_analysis_activity`, `sa_analysis_activity`, `domain_mining_activity`). Each checks `get_claude_settings().api_key` at runtime and falls back to the Phase 2.1 stub when the key is absent — so the worker still processes workflows with zero LLM cost when no key is set.
- Unit tests stay LLM-free via the autouse fixture `_force_llm_fallback_by_default` in `tests/conftest.py` (scrubs the env var + clears the settings cache for every non-integration test). Integration tests opt in with `@pytest.mark.integration`; `pyproject.toml` has `addopts = "-m 'not integration'"` by default.
- Workflow determinism: do NOT construct `BidCard(client_name=…)` inside the workflow body — the `default_factory=uuid4` / `datetime.utcnow` on pydantic fields breaks Temporal replay. Use `workflow.now()` + explicit values.
- fastembed ONNX is sync — wrap in `anyio.to_thread.run_sync` (already done in `rag/embeddings.py`).
- **Import cycle trap:** `workflows/models.py` does a late `from workflows.artifacts import ...` at the bottom so `BidState`'s artifact fields resolve. That works because `artifacts.py` imports only from `workflows.base` (and `agents.models`), not from `workflows.models`. If you add a type to `models.py` that `artifacts.py` needs, put it in `workflows/base.py` instead.
- **Docker image split:** `ai-service` and `ai-worker` use SEPARATE image tags (`bid-framework-ai-service` vs `bid-framework-ai-worker`) even though they share the Dockerfile. After editing workflow/activity code, rebuild BOTH images and force-recreate the worker container, otherwise the live worker keeps running stale bytecode silently (no error, workflow just stops at an old terminal state).
- **S3 parallel activities** are dispatched via `asyncio.gather(workflow.execute_activity(...), ...)`. If one stream errors permanently, `gather` cancels the others and the workflow fails. `return_exceptions=True` would let partial success through — add only when Phase 2.2 has real agents that sometimes degrade.
- **S9 review gate is live (Phase 2.4):** `human_review_decision` signal + earliest-target loop-back + 3-round cap → `S9_BLOCKED` on exhaustion. Seeding a non-APPROVED verdict will re-enter earlier states, so don't test signals against a production bid.
- **Phase 3.1 assembly DTO quirk:** `AssemblyInput.bid_card` / `triage` / `scoping` are typed `Any` (not their real Pydantic model) to dodge the `workflows.models ↔ artifacts.py` import cycle. On the Temporal activity side these round-trip as plain dicts with ISO-string datetimes; templates use Jinja's attr-then-dict fallback + the `| date` filter parses ISO strings. If you add a template that does `triage.some_pydantic_method()`, reach into `vars(triage)` or refactor the types to live on `workflows.base`.

## Pointers
- Root rules: `../../CLAUDE.md`
- Full architecture: `../../docs/architecture/SYSTEM_ARCHITECTURE.md`
- 11-state machine: `../../docs/states/STATE_MACHINE.md`
- Current progress: `../../CURRENT_STATE.md`
- Phase 1 delivery manifest: `../../docs/phases/PHASE_1_PLAN.md`
