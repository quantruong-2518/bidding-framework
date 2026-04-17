"""Shared DTOs for RFP parsing (adapter-agnostic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceFormat = Literal["pdf", "docx", "txt"]


class Section(BaseModel):
    """One heading + the text that follows it until the next heading."""

    heading: str
    level: int = Field(ge=0, le=6, default=0)
    text: str = ""
    page_hint: int | None = None  # best-effort; pypdf cannot always pin text to a page


class TableBlob(BaseModel):
    """Raw table captured from the source. Phase 2 keeps it as text grid; Phase 3 may upgrade to structured cells."""

    caption: str | None = None
    raw_text: str
    page_hint: int | None = None


class ParsedRFP(BaseModel):
    """Adapter-agnostic parse result. Fed into rfp_extractor for IntakeInput inference."""

    source_format: SourceFormat
    source_filename: str
    page_count: int | None = None
    sections: list[Section] = Field(default_factory=list)
    tables: list[TableBlob] = Field(default_factory=list)
    raw_text: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class BidCardSuggestion(BaseModel):
    """IntakeInput-shaped suggestion from rfp_extractor — frontend pre-fills form fields with this."""

    client_name: str = ""
    industry: str = ""
    region: str = ""
    scope_summary: str = ""
    requirement_candidates: list[str] = Field(default_factory=list)
    technology_keywords: list[str] = Field(default_factory=list)
    estimated_profile_hint: Literal["S", "M", "L", "XL"] | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ParseResponse(BaseModel):
    """Wire shape returned by POST /workflows/bid/parse-rfp."""

    parsed_rfp: ParsedRFP
    suggested_bid_card: BidCardSuggestion


__all__ = [
    "BidCardSuggestion",
    "ParseResponse",
    "ParsedRFP",
    "Section",
    "SourceFormat",
    "TableBlob",
]
