"""ParsedRFP → BidCardSuggestion heuristic mapper.

Pure text heuristics — no LLM. Good enough for first-pass auto-fill of the
BidCard form; the bid manager reviews + edits before kicking off the workflow.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from parsers.models import BidCardSuggestion, ParsedRFP, Section

logger = logging.getLogger(__name__)

# --- Industry / region dictionaries ------------------------------------------

_INDUSTRY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("banking", ("bank", "banking", "core banking", "branch", "loan", "credit card", "atm", "basel")),
    ("insurance", ("insurance", "insurer", "claims", "underwriting", "actuarial", "solvency")),
    ("healthcare", ("hospital", "clinic", "patient", "phi", "hipaa", "ehr", "healthcare")),
    ("retail", ("retail", "pos", "point-of-sale", "e-commerce", "ecommerce", "storefront")),
    ("government", ("ministry", "agency", "government", "public sector", "e-government")),
    ("manufacturing", ("mes", "factory", "plant", "scada", "iot", "manufacturing")),
    ("telco", ("telecom", "telco", "bss", "oss", "operator", "carrier")),
    ("energy", ("utility", "utilities", "energy", "grid", "substation", "oil", "gas")),
    ("logistics", ("logistics", "warehouse", "freight", "tms", "wms")),
    ("education", ("university", "school", "student", "education", "lms", "edtech")),
)

_REGION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("APAC", ("apac", "asia pacific", "vietnam", "singapore", "indonesia", "malaysia", "thailand", "philippines", "japan", "korea", "hong kong")),
    ("EMEA", ("emea", "europe", "eu", "germany", "france", "uk", "united kingdom", "middle east")),
    ("NA", ("north america", "usa", "united states", "canada", "us ")),
    ("LATAM", ("latam", "latin america", "brazil", "mexico", "argentina")),
)

# --- Technology keyword detector (kept small; extended list lives in S2 scoping) ---

_TECH_KEYWORDS = (
    "java", "spring", "python", "fastapi", "django", "nestjs", "nodejs", "node.js",
    "react", "next.js", "angular", "vue", "go", "golang", "rust", "c#", ".net",
    "postgres", "mysql", "oracle", "mongodb", "redis", "kafka", "rabbitmq",
    "kubernetes", "k8s", "docker", "aws", "azure", "gcp", "terraform",
    "rest", "graphql", "grpc", "websocket", "kafka", "airflow",
    "snowflake", "databricks", "spark", "kafka",
    "keycloak", "oauth", "saml", "sso",
)

_HEADING_REQ_RE = re.compile(
    r"requirement|scope|capabilit|functional|non-functional|nfr|sla|deliverable",
    re.IGNORECASE,
)

_MODAL_RE = re.compile(
    r"\b(?:shall|must|should|may|will|need(?:s|ed)?\s+to|is\s+required\s+to)\b",
    re.IGNORECASE,
)

_BULLET_RE = re.compile(r"^\s*(?:[-*•●◦▪]|\d+\.|[a-z]\)|[ivxlcdm]+\))\s+", re.IGNORECASE)

_CLIENT_STOPWORDS = frozenset(
    {"the", "rfp", "request", "for", "proposal", "proposal", "ltd", "ltd.", "inc", "inc.", "co", "co.", "llc", "limited"}
)


# --- Client name extraction ---------------------------------------------------


def _candidate_client_from_title(title: str) -> str:
    """Strip RFP/Proposal noise from a document title, return a plausible org name."""
    title = re.sub(r"\brfp\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"request\s+for\s+proposal", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[|\-:]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -:|")
    tokens = [t for t in title.split() if t.lower() not in _CLIENT_STOPWORDS]
    return " ".join(tokens[:5]).strip()


def _client_from_metadata(parsed: ParsedRFP) -> str:
    for key in ("author", "title", "subject"):
        value = parsed.metadata.get(key)
        if not value:
            continue
        candidate = _candidate_client_from_title(value)
        if len(candidate) >= 3:
            return candidate
    return ""


def _client_from_body(parsed: ParsedRFP) -> str:
    """Fallback: first capitalised multi-word span near the top of the doc."""
    head_text = parsed.raw_text[:1500]
    # Match "Prepared for <Org>", "Client: <Org>", etc.
    for pattern in (
        r"(?:prepared\s+for|client|issuer|sponsor|on\s+behalf\s+of)\s*[:\-]\s*([A-Z][A-Za-z0-9&.,' \-]{2,60})",
        r"\b([A-Z][A-Za-z0-9&.,' \-]{2,60}\s+(?:Bank|Insurance|Group|Ltd|Limited|Corporation|Corp|LLC|Inc|Pte))\b",
    ):
        match = re.search(pattern, head_text)
        if match:
            candidate = _candidate_client_from_title(match.group(1))
            if len(candidate) >= 3:
                return candidate
    return ""


# --- Industry / region ------------------------------------------------------


def _score_industry(text: str) -> str:
    lowered = text.lower()
    scores = Counter[str]()
    for industry, keywords in _INDUSTRY_KEYWORDS:
        for kw in keywords:
            scores[industry] += lowered.count(kw)
    if not scores:
        return ""
    best, count = scores.most_common(1)[0]
    return best if count >= 2 else ""


def _score_region(text: str) -> str:
    lowered = text.lower()
    for region, keywords in _REGION_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return region
    return ""


# --- Requirement candidates -------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    # A deliberately simple splitter — good enough for requirement line detection.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _is_requirement_section(section: Section) -> bool:
    return bool(_HEADING_REQ_RE.search(section.heading))


def _extract_bullets(section: Section) -> list[str]:
    lines = [line.strip() for line in section.text.splitlines() if line.strip()]
    bullets: list[str] = []
    for line in lines:
        if _BULLET_RE.match(line):
            bullets.append(_BULLET_RE.sub("", line).strip())
    return bullets


def _extract_modal_sentences(text: str) -> list[str]:
    return [s for s in _split_sentences(text) if _MODAL_RE.search(s)]


def _dedupe(strings: list[str], cap: int = 50) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in strings:
        normalized = re.sub(r"\s+", " ", s).strip().rstrip(".").lower()
        if normalized in seen or len(normalized) < 8:
            continue
        seen.add(normalized)
        out.append(s.strip())
        if len(out) >= cap:
            break
    return out


def _collect_requirements(parsed: ParsedRFP) -> list[str]:
    collected: list[str] = []

    # 1) Sections whose heading mentions requirements/scope/capability: pull bullets + modal sentences.
    for section in parsed.sections:
        if _is_requirement_section(section):
            collected.extend(_extract_bullets(section))
            collected.extend(_extract_modal_sentences(section.text))

    # 2) Whole-document modal-verb sentences as a fallback if nothing found.
    if not collected:
        collected.extend(_extract_modal_sentences(parsed.raw_text))

    return _dedupe(collected)


# --- Technology keywords + profile ------------------------------------------


def _collect_tech_keywords(text: str) -> list[str]:
    lowered = text.lower()
    hits = [kw for kw in _TECH_KEYWORDS if kw in lowered]
    # Deduplicate while preserving appearance order.
    seen: set[str] = set()
    out: list[str] = []
    for kw in hits:
        if kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out[:15]


def _guess_profile(requirement_count: int, page_count: int | None, tables: int) -> str | None:
    """Order-of-magnitude hint only — bid manager confirms profile at triage."""
    if requirement_count == 0 and not page_count:
        return None
    size_signal = (page_count or 0) + 2 * tables + int(requirement_count / 5)
    if size_signal <= 8:
        return "S"
    if size_signal <= 20:
        return "M"
    if size_signal <= 45:
        return "L"
    return "XL"


# --- Scope summary ----------------------------------------------------------


def _scope_summary(parsed: ParsedRFP) -> str:
    """Pick the first non-empty paragraph from sections most likely to describe scope."""
    preferred_headings = re.compile(
        r"scope|overview|executive\s+summary|introduction|objective|background",
        re.IGNORECASE,
    )
    for section in parsed.sections:
        if preferred_headings.search(section.heading) and section.text.strip():
            paragraph = section.text.strip().split("\n\n")[0].strip()
            if len(paragraph) >= 40:
                return re.sub(r"\s+", " ", paragraph)[:600]
    # Fallback: first ~400 chars of the document body.
    return re.sub(r"\s+", " ", parsed.raw_text[:400]).strip()


# --- Confidence -------------------------------------------------------------


def _confidence(
    client_name: str,
    industry: str,
    region: str,
    requirement_count: int,
) -> float:
    signals = 0
    if client_name:
        signals += 1
    if industry:
        signals += 1
    if region:
        signals += 1
    if requirement_count >= 3:
        signals += 1
    if requirement_count >= 10:
        signals += 1
    return round(min(0.9, signals / 5.0 + 0.1), 2)


# --- Public entry point -----------------------------------------------------


def extract_bid_card(parsed: ParsedRFP) -> BidCardSuggestion:
    """Best-effort IntakeInput-shaped suggestion. Safe to call on malformed parses."""
    requirements = _collect_requirements(parsed)
    industry = _score_industry(parsed.raw_text)
    region = _score_region(parsed.raw_text)
    tech_keywords = _collect_tech_keywords(parsed.raw_text)
    client_name = _client_from_metadata(parsed) or _client_from_body(parsed)
    scope_summary = _scope_summary(parsed)
    profile_hint = _guess_profile(len(requirements), parsed.page_count, len(parsed.tables))

    suggestion = BidCardSuggestion(
        client_name=client_name,
        industry=industry,
        region=region,
        scope_summary=scope_summary,
        requirement_candidates=requirements,
        technology_keywords=tech_keywords,
        estimated_profile_hint=profile_hint,  # type: ignore[arg-type]
        confidence=_confidence(client_name, industry, region, len(requirements)),
    )
    logger.info(
        "rfp_extractor.done client=%r industry=%r region=%r reqs=%d tech=%d conf=%.2f",
        suggestion.client_name,
        suggestion.industry,
        suggestion.region,
        len(suggestion.requirement_candidates),
        len(suggestion.technology_keywords),
        suggestion.confidence,
    )
    return suggestion


__all__ = ["extract_bid_card"]
