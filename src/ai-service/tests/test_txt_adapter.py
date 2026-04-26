"""S0.5 Wave 2A — txt_adapter unit tests."""

from __future__ import annotations

import pytest

from parsers.txt_adapter import parse_txt


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401
    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    yield None


def test_parse_txt_creates_single_section_spanning_all_lines() -> None:
    body = b"line one\nline two\nline three"
    parsed = parse_txt(body, "doc.txt")
    assert len(parsed.sections) == 1
    section = parsed.sections[0]
    assert section["heading"] == "doc.txt"
    assert section["line_range"] == (1, 3)
    assert section["text"] == body.decode("utf-8")


def test_parse_txt_handles_empty_body() -> None:
    parsed = parse_txt(b"", "empty.txt")
    assert parsed.raw_text == ""
    # Single section with line_range still valid (1,1).
    assert parsed.sections[0]["line_range"] == (1, 1)
