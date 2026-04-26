"""S0.5 Wave 2A — md_adapter unit tests."""

from __future__ import annotations

import pytest

from parsers.md_adapter import parse_md


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def test_parse_md_extracts_headings_as_sections() -> None:
    body = b"# Top\n\nIntro\n\n## Sub A\n\nA body\n\n## Sub B\n\nB body\n"
    parsed = parse_md(body, "doc.md")
    headings = [s["heading"] for s in parsed.sections]
    assert "Top" in headings
    assert "Sub A" in headings
    assert "Sub B" in headings


def test_parse_md_strips_frontmatter_into_metadata() -> None:
    body = b'---\ntitle: "RFP"\nauthor: bid-team\n---\n# Heading\n\nBody.\n'
    parsed = parse_md(body, "doc.md")
    assert parsed.metadata.get("title") == "RFP"
    assert parsed.metadata.get("author") == "bid-team"
    # Frontmatter not in raw body.
    assert "title:" not in parsed.raw_text
    assert "Heading" in parsed.raw_text


def test_parse_md_handles_invalid_utf8_with_replacement() -> None:
    body = b"# Title\n\nValid\n\n\xff\xfe garbage byte"
    parsed = parse_md(body, "doc.md")
    assert "Title" in [s["heading"] for s in parsed.sections]
    # Should not raise; raw_text contains some replacement chars.
    assert parsed.size_bytes == len(body)
