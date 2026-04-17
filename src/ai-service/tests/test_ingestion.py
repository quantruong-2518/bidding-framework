"""Unit tests for the Obsidian vault ingestion package."""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from config.ingestion import IngestionSettings
from ingestion.ingestion_service import IngestionService
from ingestion.link_extractor import build_edges, extract_links
from ingestion.vault_parser import parse_note
from ingestion.vault_scanner import scan_vault
from ingestion.watcher import VaultWatcher


def _write(path: Path, content: str) -> Path:
    """Helper: ensure parent exists, write utf-8, return path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def _fake_vault(tmp_path: Path) -> Path:
    """Build a small fake vault with 4 md files + .obsidian to skip."""
    root = tmp_path / "vault"
    root.mkdir()
    _write(
        root / "projects" / "alpha.md",
        """
        ---
        project_id: proj-alpha-01
        client: AlphaCo
        domain: banking
        year: 2024
        doc_type: project
        tags: [core, migration]
        ---
        # Alpha

        Links to [[microservices]] and [[event-sourcing|ES]] and [[AlphaCo]].

        ## Outcomes
        Great.
        """,
    )
    _write(
        root / "projects" / "beta.md",
        """
        ---
        project_id: proj-beta-02
        client: BetaCo
        domain: e-commerce
        year: 2025
        doc_type: project
        ---
        # Beta

        Linked: [[nextjs]].
        """,
    )
    _write(
        root / "technologies" / "microservices.md",
        """
        ---
        doc_type: technology
        domain: architecture
        ---
        # Microservices

        See [[alpha]].
        """,
    )
    _write(
        root / "lessons" / "risk.md",
        """
        ---
        doc_type: lesson
        ---
        # Risk

        No links here.
        """,
    )
    # A .obsidian directory that must be skipped.
    _write(root / ".obsidian" / "app.json", "{}\n")
    _write(root / ".obsidian" / "notes-inside.md", "# should be skipped\n")
    return root


def test_parse_note_frontmatter_and_links(tmp_path: Path) -> None:
    root = _fake_vault(tmp_path)
    note = parse_note(root / "projects" / "alpha.md", vault_root=root)
    assert note.frontmatter["project_id"] == "proj-alpha-01"
    assert note.frontmatter["client"] == "AlphaCo"
    assert note.frontmatter["year"] == 2024
    assert note.frontmatter["doc_type"] == "project"
    assert note.frontmatter["tags"] == ["core", "migration"]
    assert "microservices" in note.links
    assert "event-sourcing" in note.links
    assert "AlphaCo" in note.links
    assert note.headings == ["Alpha", "Outcomes"]
    assert note.content_hash  # sha256 is populated


def test_link_extractor_aliases() -> None:
    text = "See [[target|display text]] and [[other]] and [[sub/page|alias]]."
    assert extract_links(text) == ["target", "other", "page"]


def test_build_edges_contains_source_and_context(tmp_path: Path) -> None:
    root = _fake_vault(tmp_path)
    note = parse_note(root / "projects" / "alpha.md", vault_root=root)
    edges = build_edges(note)
    assert {e.target_name for e in edges} >= {"microservices", "event-sourcing", "AlphaCo"}
    for edge in edges:
        assert edge.source_path.endswith("alpha.md")
        assert edge.context  # non-empty


@pytest.mark.asyncio
async def test_scanner_skips_obsidian_dir(tmp_path: Path) -> None:
    root = _fake_vault(tmp_path)
    relatives: list[str] = []
    async for note in scan_vault(root):
        relatives.append(str(note.relative_path))
    assert len(relatives) == 4
    assert not any(".obsidian" in r for r in relatives)


def _make_settings(tmp_path: Path, root: Path) -> IngestionSettings:
    """Build an IngestionSettings instance rooted at tmp_path."""
    return IngestionSettings(
        vault_path=root,
        poll_interval_seconds=0.05,
        debounce_ms=50,
        hash_cache_path=tmp_path / "hashes.json",
        graph_snapshot_path=tmp_path / "graph.json",
    )


@pytest.mark.asyncio
async def test_initial_index_invokes_indexer_for_each_md(tmp_path: Path) -> None:
    root = _fake_vault(tmp_path)
    calls: list[tuple[str, dict]] = []

    async def fake_indexer(client, path, metadata_overrides):
        calls.append((path, dict(metadata_overrides or {})))
        return 3  # pretend 3 chunks indexed

    service = IngestionService(
        qdrant_client=object(),
        settings=_make_settings(tmp_path, root),
        indexer=fake_indexer,
    )
    count = await service.initial_index(root)
    assert count == 4
    assert len(calls) == 4
    # Frontmatter flows through as metadata overrides.
    alpha_call = next(c for c in calls if c[0].endswith("alpha.md"))
    overrides = alpha_call[1]
    assert overrides["client"] == "AlphaCo"
    assert overrides["domain"] == "banking"
    assert overrides["year"] == 2024
    assert overrides["doc_type"] == "project"
    assert overrides["id"] == "proj-alpha-01"
    # Graph populated.
    snapshot = service.graph.snapshot()
    assert snapshot.note_count == 4
    assert snapshot.edge_count >= 3
    assert snapshot.doc_types.get("project") == 2
    # Snapshot file written.
    assert (tmp_path / "graph.json").exists()


@pytest.mark.asyncio
async def test_on_file_change_skips_when_hash_unchanged(tmp_path: Path) -> None:
    root = _fake_vault(tmp_path)
    calls: list[str] = []

    async def fake_indexer(client, path, metadata_overrides):
        calls.append(path)
        return 1

    service = IngestionService(
        qdrant_client=object(),
        settings=_make_settings(tmp_path, root),
        indexer=fake_indexer,
    )
    await service.initial_index(root)
    first_call_count = len(calls)

    target = root / "technologies" / "microservices.md"
    changed = await service.on_file_change(target)
    assert changed is False
    assert len(calls) == first_call_count

    # Mutating the file makes on_file_change index again.
    target.write_text(target.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8")
    changed = await service.on_file_change(target)
    assert changed is True
    assert len(calls) == first_call_count + 1


@pytest.mark.asyncio
async def test_watcher_debounces_bursts(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    fired: list[Path] = []

    async def on_change(path: Path) -> None:
        fired.append(path)

    watcher = VaultWatcher(root, on_change, debounce_ms=50, poll_interval_seconds=1.0)
    # Prime the loop ref without starting watch().
    watcher._loop = asyncio.get_event_loop()
    p1 = root / "a.md"
    p2 = root / "b.md"
    # Fire 5 synthetic events for p1 within the debounce window, plus 3 for p2.
    for _ in range(5):
        watcher.enqueue(p1)
    for _ in range(3):
        watcher.enqueue(p2)
    await asyncio.sleep(0.2)

    assert sorted(str(p) for p in fired) == sorted([str(p1), str(p2)])
