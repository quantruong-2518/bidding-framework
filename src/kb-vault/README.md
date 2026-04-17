# Bid Framework — Knowledge Vault

This is the seed Obsidian vault consumed by the ingestion service (Task 1.5). SMEs curate
knowledge here; the watcher reindexes changes into Qdrant.

## Conventions
- Every note has YAML frontmatter with at least `doc_type` and `tags`.
- Projects also carry `project_id`, `client`, `domain`, `year`.
- Use `[[wiki-links]]` generously — every link becomes an edge in the knowledge graph.
- Folders: `projects/`, `clients/`, `technologies/`, `templates/`, `lessons/`.
- Filenames use kebab-case; the stem is the link target (`[[acme]]` -> `clients/acme.md`).

## doc_type values
- `project` — delivered engagement case study
- `client` — client profile / relationship history
- `technology` — capability / stack write-up
- `template` — reusable WBS / HLD / proposal skeleton
- `lesson` — cross-project lessons learned

## Do not edit
- `.obsidian/` — Obsidian state
- Generated per-bid folders (Phase 2) will land under `bids/<bid-id>/`
