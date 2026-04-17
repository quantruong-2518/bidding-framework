# ai-service (Python) — AI Bidding Framework

> Local CLAUDE.md. Root config lives at `../../CLAUDE.md`. Read that first for project-wide rules. This file adds service-specific context.

## Role
- Python 3.12 / FastAPI app + Temporal workers + LangGraph agents + RAG pipeline + Obsidian ingestion.
- Listens on port `8001`. Temporal worker is a separate entrypoint (`worker.py`) — run alongside the FastAPI app in prod.
- Upstream: NestJS api-gateway calls us at `http://ai-service:8001/workflows/bid/*`.
- Downstream: Qdrant (`qdrant:6333`), Temporal (`temporal:7233`), Redis (`redis:6379`), Postgres (`postgres:5432`), Anthropic API.

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

## File tour (Phase 1)
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
    models.py                # All Pydantic DTOs (BidCard, BidState, TriageDecision, …)
                             # WorkflowState literal = single source of truth for state names
    bid_workflow.py          # BidWorkflow @workflow.defn (S0 → S1 gate → S2)
    router.py                # FastAPI: /start, /start-from-card, /{id}/triage-signal, /{id}

  activities/
    intake.py                # S0: parse raw RFP → BidCard
    triage.py                # S1: calls agents/triage_agent.py::score
    scoping.py               # S2: requirement decomposition + stream assignment
    ba_analysis.py           # S3a: wraps agents/ba_agent.py (NOT yet registered in worker.py)

  agents/
    triage_agent.py          # Stub deterministic scorer (swap-point for LLM)
    ba_agent.py              # LangGraph 4-node: retrieve → extract(Haiku) → synth(Sonnet) → critique(Sonnet)
    models.py                # BARequirements, BusinessRequirementsDraft, etc.
    prompts/ba_agent.py      # Versioned system prompts for BA graph

  tools/
    claude_client.py         # AsyncAnthropic wrapper with cache_control: ephemeral (prompt caching)
    kb_search.py             # Qdrant search wrapper; degrades to [] on error

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
- `ba_analysis_activity` exists but is NOT yet registered in `worker.py` — by design, Phase 2.2 wires S3a/b/c in parallel.
- Workflow determinism: do NOT construct `BidCard(client_name=…)` inside the workflow body — the `default_factory=uuid4` / `datetime.utcnow` on pydantic fields breaks Temporal replay. Use `workflow.now()` + explicit values.
- fastembed ONNX is sync — wrap in `anyio.to_thread.run_sync` (already done in `rag/embeddings.py`).

## Pointers
- Root rules: `../../CLAUDE.md`
- Full architecture: `../../docs/architecture/SYSTEM_ARCHITECTURE.md`
- 11-state machine: `../../docs/states/STATE_MACHINE.md`
- Current progress: `../../CURRENT_STATE.md`
- Phase 1 delivery manifest: `../../docs/phases/PHASE_1_PLAN.md`
