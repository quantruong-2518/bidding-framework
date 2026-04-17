# kb-vault (Obsidian) — AI Bidding Framework Knowledge Base

> Local CLAUDE.md. Root config lives at `../../CLAUDE.md`. Read that first. This file adds vault-specific conventions for authors and agents.

## Role
- Obsidian vault that seeds the RAG knowledge base. SMEs curate markdown notes here; the ingestion service (`../ai-service/ingestion/`) watches this tree, parses each note, extracts `[[links]]`, and pushes chunks to Qdrant.
- Git-synced → version control + audit trail.
- Phase 2 will add per-bid workspaces under `bids/<bid-id>/` using this same structure.

## Folder structure
```
kb-vault/
  README.md                       # vault conventions (author-facing)
  .obsidian/                      # minimal config so Obsidian opens cleanly
    app.json
    workspace.json
  projects/                       # case studies of past delivered projects
  clients/                        # client profiles (industry, size, history)
  technologies/                   # tech topic notes (microservices, k8s, temporal-io, …)
  templates/                      # reusable skeletons (WBS, HLD, proposal)
  lessons/                        # lessons learned — estimation pitfalls, integration risks, …
```

## Note conventions (REQUIRED for ingestion)

Every note must start with YAML frontmatter:

```yaml
---
id: <slug-unique-within-doc_type>
client: <client-name-or-omit>          # projects + clients only
project_id: <slug>                     # projects only
domain: banking|healthcare|ecommerce|saas|telco|manufacturing|…
year: 2023
doc_type: project|client|technology|template|lesson
tags: [microservices, event-sourcing]
---
```

- `doc_type` is used by the indexer to build metadata filters — keep values from the enum above (new values OK, but align with `src/ai-service/rag/retriever.py` filter examples).
- Inline lists (`tags: [a, b]`) and block-dash lists are both accepted by the parser.
- Prefer semantic filenames: `acme-core-banking.md`, `template-wbs-banking.md`, `lesson-estimation-pitfalls.md`.

## Wiki-links policy
- Use `[[note-stem]]` liberally — each link becomes a graph edge persisted to `vault-graph.json`.
- Alias allowed: `[[microservices|microservice architecture]]` → target is `microservices`.
- Nested path is OK: `[[technologies/temporal-io]]`.
- `![[embed]]` syntax is ignored by the parser (no issue, just not indexed).
- Dangling links are surfaced in the ingestion snapshot — create the target note or fix the link.

## Content style
- 2–6 paragraphs per note is the sweet spot for RAG chunking (heading-aware splitter).
- Use `##` headings — chunker splits on them first.
- Include concrete numbers/dates/tech names — they become retrievable signals.
- Avoid secrets: no real client credentials, API keys, or PII.

## Ingestion operation
```bash
# One-shot (from repo root, assumes Qdrant is up)
cd src/ai-service && poetry run python -m ingestion --vault ../kb-vault

# Watch mode — re-index on file change
cd src/ai-service && poetry run python -m ingestion --vault ../kb-vault --watch
```

Artifacts produced:
- Qdrant collection `bid_knowledge` (named vectors: `dense` + `sparse`) — payload includes `client`, `domain`, `project_id`, `year`, `doc_type`, `source_path`, `id`, `parent_doc_id`, `chunk_index`.
- `/tmp/bid-framework/ingestion-hashes.json` — content-hash cache (skips unchanged files).
- `/tmp/bid-framework/vault-graph.json` — knowledge-graph snapshot (nodes + outgoing/incoming edges + dangling links).

## Known gotchas
- If you rename a note, the old Qdrant points remain — run a full re-seed or delete by `parent_doc_id` filter.
- Linking by filename stem only (not path). Collisions are surfaced as "ambiguous" in the graph snapshot.
- `.obsidian/` is ignored by the scanner — keep per-user workspace config out of Git if you add local plugins.

## Pointers
- Root rules: `../../CLAUDE.md`
- Ingestion code: `../ai-service/ingestion/`
- RAG/indexer: `../ai-service/rag/indexer.py`, `../ai-service/rag/retriever.py`
- Architecture (Obsidian integration): `../../docs/architecture/SYSTEM_ARCHITECTURE.md`
- Current progress: `../../CURRENT_STATE.md`
