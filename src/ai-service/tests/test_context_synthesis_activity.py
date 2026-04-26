"""S0.5 Wave 2A — context_synthesis activity unit tests.

Covers preview mode + materialize mode + stub fallback. The activity body
is the same coroutine the Temporal worker invokes, so these tests run on
host when temporalio is installed (Docker pytest path); skipped otherwise.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


# Skip the whole module when temporalio is missing — context_synthesis activity
# pulls in @activity.defn at import time. Docker pytest run still covers these.
pytest.importorskip("temporalio", reason="temporalio not on host; covered in Docker")

from activities.context_synthesis import (  # noqa: E402  (intentional after importorskip)
    AtomEntry,
    ContextSynthesisInput,
    ContextSynthesisOutput,
    _run_materialize,
    _run_preview,
    _safe_file_id,
    context_synthesis_activity,
)
from kb_writer.atom_emitter import REQUIREMENTS_SUBDIR  # noqa: E402
from kb_writer.manifest_writer import MANIFEST_FILENAME  # noqa: E402
from kb_writer.pack_builder import PACKS_SUBDIR  # noqa: E402
from workflows.base import (  # noqa: E402
    AtomExtraction,
    AtomFrontmatter,
    AtomLinks,
    AtomSource,
    AtomVerification,
    IntakeFile,
    Manifest,
    ManifestFile,
)


def _make_intake_file(name: str, body: str) -> IntakeFile:
    encoded = base64.b64encode(body.encode("utf-8")).decode("ascii")
    return IntakeFile(
        name=name,
        mime="text/plain" if name.endswith(".txt") else "text/markdown",
        content_b64=encoded,
        size_bytes=len(body),
    )


@pytest.mark.asyncio
async def test_preview_mode_with_stub_path_returns_atoms_anchor_summary() -> None:
    files = [
        _make_intake_file(
            "rfp.md",
            "# Banking RFP\n\n- The system shall support SSO\n- HIPAA required\n",
        )
    ]
    out = await _run_preview(
        ContextSynthesisInput(
            mode="preview",
            parse_session_id="session-uuid-1",
            tenant_id="acme-bank",
            lang="en",
            files=files,
        )
    )
    assert isinstance(out, ContextSynthesisOutput)
    assert out.mode == "preview"
    assert len(out.atoms) >= 1
    # Stub path → ai_generated False, parser heuristic_v1.
    assert all(a.frontmatter.ai_generated is False for a in out.atoms)
    assert out.anchor_md  # template-based stub returns non-empty
    assert out.summary_md
    # Manifest has one entry for our file.
    assert out.manifest is not None
    assert len(out.manifest.files) == 1


@pytest.mark.asyncio
async def test_preview_mode_classifies_files_via_heuristic() -> None:
    files = [_make_intake_file("Banking_Core_RFP_v1.md", "# RFP\nbody")]
    out = await _run_preview(
        ContextSynthesisInput(
            mode="preview",
            parse_session_id="session-uuid-2",
            tenant_id="acme",
            files=files,
        )
    )
    assert out.sources_preview[0]["role"] == "rfp"


@pytest.mark.asyncio
async def test_preview_mode_handles_empty_files_list() -> None:
    out = await _run_preview(
        ContextSynthesisInput(
            mode="preview",
            parse_session_id="session-uuid-3",
            tenant_id="acme",
            files=[],
        )
    )
    assert out.atoms == []
    assert out.anchor_md  # stub still returns template
    assert out.manifest is not None
    assert out.manifest.files == []


@pytest.mark.asyncio
async def test_materialize_mode_writes_atoms_anchor_summary_to_vault(
    tmp_path: Path,
) -> None:
    bid_id = str(uuid4())
    atom = AtomFrontmatter(
        id="REQ-F-001",
        type="functional",
        priority="MUST",
        category="user_management",
        source=AtomSource(file="sources/01-rfp.md"),
        extraction=AtomExtraction(parser="heuristic_v1", confidence=0.5),
        verification=AtomVerification(),
        links=AtomLinks(),
        tenant_id="acme",
        bid_id=bid_id,
    )
    payload = {
        "atoms": [
            AtomEntry(frontmatter=atom, body_markdown="# REQ-F-001\n\n- claim").model_dump(mode="json")
        ],
        "anchor_md": "# Project Anchor\n\nAcme Bank context.",
        "summary_md": "# Summary\n\nBackground...",
        "open_questions": ["Q1"],
        "conflicts": [],
        "manifest": Manifest(
            bid_id=bid_id,
            tenant_id="acme",
            session_id="session-1",
            files=[ManifestFile(file_id="01", original_name="01.pdf")],
        ).model_dump(mode="json"),
    }

    out = await _run_materialize(
        ContextSynthesisInput(
            mode="materialize",
            parse_session_id="session-1",
            tenant_id="acme",
            bid_id=bid_id,
            payload=payload,
            vault_root=str(tmp_path),
            files=[],
        )
    )
    assert out.mode == "materialize"
    assert len(out.atoms) == 1

    # Verify on-disk artifacts.
    bid_root = tmp_path / "bids" / bid_id
    assert (bid_root / MANIFEST_FILENAME).exists()
    assert (bid_root / REQUIREMENTS_SUBDIR / "req-f-001.md").exists()
    assert (bid_root / "anchor.md").exists()
    assert (bid_root / "summary.md").exists()
    # Pack rebuild ran.
    assert (bid_root / PACKS_SUBDIR / "review-pack.md").exists()


@pytest.mark.asyncio
async def test_materialize_mode_writes_conflicts_when_present(
    tmp_path: Path,
) -> None:
    bid_id = str(uuid4())
    payload = {
        "atoms": [],
        "anchor_md": "",
        "summary_md": "",
        "conflicts": [
            {
                "topic": "priority_clash",
                "severity": "HIGH",
                "description": "MUST vs WONT",
                "atoms": ["REQ-F-001", "REQ-F-002"],
                "files": ["01-rfp", "02-appendix"],
                "proposed_resolution": "Resolve with bid manager.",
            }
        ],
    }
    await _run_materialize(
        ContextSynthesisInput(
            mode="materialize",
            parse_session_id="session-1",
            tenant_id="acme",
            bid_id=bid_id,
            payload=payload,
            vault_root=str(tmp_path),
            files=[],
        )
    )
    conflict_path = tmp_path / "bids" / bid_id / "conflicts.md"
    assert conflict_path.exists()
    text = conflict_path.read_text()
    assert "priority_clash" in text
    assert "Resolve with bid manager." in text


@pytest.mark.asyncio
async def test_safe_file_id_normalises_special_chars() -> None:
    assert _safe_file_id("Banking RFP v1.pdf") == "banking-rfp-v1"
    assert _safe_file_id("") == "file"


@pytest.mark.asyncio
async def test_context_synthesis_activity_dispatches_by_mode(tmp_path: Path) -> None:
    """The activity surface itself routes preview vs materialize."""
    out_preview = await context_synthesis_activity(
        ContextSynthesisInput(
            mode="preview",
            parse_session_id="session-x",
            tenant_id="acme",
            files=[_make_intake_file("doc.md", "- Required to do X")],
        )
    )
    assert out_preview.mode == "preview"

    out_mat = await context_synthesis_activity(
        ContextSynthesisInput(
            mode="materialize",
            parse_session_id="session-x",
            tenant_id="acme",
            bid_id=str(uuid4()),
            payload={"atoms": [], "anchor_md": "", "summary_md": ""},
            vault_root=str(tmp_path),
            files=[],
        )
    )
    assert out_mat.mode == "materialize"
