from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


CANONICAL_FILTER_KEYS = {
    "lang",
    "category",
    "topic",
    "institution",
    "region",
    "source_policy",
    "source_name",
    "doc_id",
    "chunk_id",
    "origin_url",
    "title",
    "path",
}

_GENERIC_PATH_SEGMENTS = {
    "data",
    "docs",
    "doc",
    "content",
    "contents",
    "corpus",
    "rag",
    "rag-corpus",
    "sources",
    "source",
    "files",
    "texts",
    "text",
    "articles",
    "article",
    "notes",
    "note",
    "reports",
    "report",
    "datasets",
    "dataset",
    "news",
    "announcements",
    "announcement",
    "reference",
    "references",
    "research",
    "policy",
    "policies",
    "internal",
    "external",
}

_REGION_ALIASES = {
    "global": "global",
    "world": "global",
    "international": "global",
    "us": "us",
    "usa": "us",
    "united-states": "us",
    "uk": "uk",
    "united-kingdom": "uk",
    "eu": "eu",
    "europe": "eu",
    "china": "china",
    "cn": "china",
    "hong-kong": "hong-kong",
    "hk": "hong-kong",
}

_KEY_ALIASES = {
    "language": "lang",
    "locale": "lang",
    "type": "category",
    "doc_type": "category",
    "document_type": "category",
    "content_type": "category",
    "evidence_type": "category",
    "kind": "category",
    "subject": "topic",
    "theme": "topic",
    "tag": "topic",
    "tags": "topic",
    "organization": "institution",
    "organisation": "institution",
    "org": "institution",
    "agency": "institution",
    "publisher": "institution",
    "country": "region",
    "geo": "region",
    "geography": "region",
    "location": "region",
    "market": "region",
    "source_tier": "source_policy",
    "trust_level": "source_policy",
    "authority": "source_policy",
    "policy": "source_policy",
}

_CATEGORY_ALIASES = {
    "annual-report": "report",
    "financial-report": "report",
    "whitepaper": "report",
    "white-paper": "report",
    "filing": "report",
    "research-report": "report",
    "report": "report",
    "dataset": "data",
    "data": "data",
    "statistics": "data",
    "statistical": "data",
    "table": "data",
    "factsheet": "data",
    "fact-sheet": "data",
    "press-release": "announcement",
    "press": "announcement",
    "release": "announcement",
    "announcement": "announcement",
    "bulletin": "announcement",
    "update": "news",
    "updates": "news",
    "news": "news",
    "newsroom": "news",
    "article": "news",
    "blog": "news",
    "reference": "reference",
    "encyclopedia": "reference",
    "wiki": "reference",
    "policy": "policy",
    "guideline": "policy",
    "guidance": "policy",
    "paper": "research",
    "study": "research",
    "research": "research",
    "academic": "research",
}

_SOURCE_POLICY_ALIASES = {
    "official": "official",
    "government": "official",
    "gov": "official",
    "first-party": "official",
    "first_party": "official",
    "institutional": "institutional",
    "organization": "institutional",
    "organisation": "institutional",
    "org": "institutional",
    "academic": "academic",
    "research": "academic",
    "media": "media",
    "editorial": "media",
    "press": "media",
    "newsroom": "media",
    "reference": "reference",
    "wiki": "reference",
    "community": "community",
    "user-generated": "community",
    "user_generated": "community",
    "forum": "community",
    "internal": "internal",
    "private": "internal",
}

_CATEGORY_HINTS = {
    "report": ("annual report", "financial report", "report", "filing", "whitepaper", "white paper"),
    "data": ("dataset", "statistics", "statistical", "data table", "fact sheet", "factsheet", "census"),
    "announcement": ("press release", "announcement", "official release", "bulletin"),
    "news": ("news", "update", "latest", "blog", "newsroom"),
    "policy": ("policy", "guideline", "guidance", "standard"),
    "research": ("study", "paper", "journal", "research"),
    "reference": ("reference", "encyclopedia", "wiki"),
}


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return value.strip("-")


def normalize_taxonomy_key(key: str) -> str:
    normalized = _slug(key)
    return _KEY_ALIASES.get(normalized, normalized)


def normalize_taxonomy_value(key: str, value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return ""

    normalized = _slug(text)
    if key == "lang":
        if normalized in {"zh-cn", "zh-hans", "zh-hant", "chinese"}:
            return "zh"
        if normalized in {"en-us", "en-gb", "english"}:
            return "en"
        if normalized in {"zh", "en", "mixed", "unknown"}:
            return normalized
        return normalized or text.lower()
    if key == "category":
        return _CATEGORY_ALIASES.get(normalized, normalized or text.lower())
    if key == "source_policy":
        return _SOURCE_POLICY_ALIASES.get(normalized, normalized or text.lower())
    if key == "region":
        return _REGION_ALIASES.get(normalized, normalized or text.lower())
    if key in {"topic", "institution"}:
        return normalized or text.lower()
    return text.strip()


def _iter_raw_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[Any] = []
        for item in value:
            out.extend(_iter_raw_values(item))
        return out
    if isinstance(value, str):
        return [part.strip() for part in value.split(",")]
    return [value]


def ensure_taxonomy_list(value: Any) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in _iter_raw_values(value):
        text = str(item if item is not None else "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def normalize_rag_filters(filters: dict[str, Any] | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_value in (filters or {}).items():
        key = normalize_taxonomy_key(str(raw_key) if raw_key is not None else "")
        values = []
        seen = set()
        for item in _iter_raw_values(raw_value):
            value = normalize_taxonomy_value(key, item)
            if not key or not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
            if len(values) >= 4:
                break
        if not key or not values:
            continue
        normalized[key] = values
        if len(normalized) >= 6:
            break
    return normalized


def format_rag_filters(filters: dict[str, Any] | None) -> str:
    normalized = normalize_rag_filters(filters)
    if not normalized:
        return "{}"
    parts = []
    for key in sorted(normalized):
        parts.append(f"{key}={ '|'.join(normalized[key]) }")
    return "; ".join(parts)


def _guess_category(text_blob: str) -> str | None:
    lowered = (text_blob or "").lower()
    for category, hints in _CATEGORY_HINTS.items():
        if any(hint in lowered for hint in hints):
            return category
    if lowered.endswith(".pdf"):
        return "report"
    return None


def _guess_source_policy(metadata: dict[str, Any]) -> str | None:
    origin_url = str(metadata.get("origin_url") or "").strip().lower()
    source_name = str(metadata.get("source_name") or "").strip().lower()
    institution = str(metadata.get("institution") or "").strip().lower()
    category = str(metadata.get("category") or "").strip().lower()
    path = str(metadata.get("path") or "").strip().lower()

    netloc = urlparse(origin_url).netloc.lower()
    if netloc.endswith(".gov") or netloc.endswith(".edu"):
        return "official"
    if any(token in path for token in ("official", "government", "ministry", "department")):
        return "official"
    if any(token in source_name for token in ("official", "government", "ministry", "department")):
        return "official"
    if any(token in institution for token in ("un", "who", "world-bank", "imf", "nasa", "government", "ministry")):
        return "official"
    if category in {"report", "data", "policy"}:
        return "institutional"
    if category == "research":
        return "academic"
    if category == "reference":
        return "reference"
    if category in {"news", "announcement"}:
        return "media"
    return None


def _guess_topic(path: str) -> str | None:
    for raw_part in path.replace("\\", "/").split("/"):
        part = _slug(raw_part)
        if not part or part in _GENERIC_PATH_SEGMENTS or part.isdigit():
            continue
        if len(part) <= 2:
            continue
        return part
    return None


def _guess_region(path: str) -> str | None:
    for raw_part in path.replace("\\", "/").split("/"):
        region = _REGION_ALIASES.get(_slug(raw_part))
        if region:
            return region
    return None


def normalize_taxonomy_metadata(
    metadata: dict[str, Any] | None,
    *,
    title: str = "",
    source_name: str = "",
    path: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, raw_value in dict(metadata or {}).items():
        key = normalize_taxonomy_key(str(raw_key))
        if key in CANONICAL_FILTER_KEYS:
            values = []
            seen = set()
            for item in _iter_raw_values(raw_value):
                value = normalize_taxonomy_value(key, item)
                if not value or value in seen:
                    continue
                seen.add(value)
                values.append(value)
            if values:
                out[key] = values[0] if len(values) == 1 else values
            continue
        out[str(raw_key)] = raw_value

    if source_name and not out.get("source_name"):
        out["source_name"] = source_name.strip()
    if path and not out.get("path"):
        out["path"] = path.replace("\\", "/")

    text_blob = " ".join(part for part in [title, source_name, path, str(out.get("path") or "")] if part)
    if not out.get("category"):
        guessed_category = _guess_category(text_blob)
        if guessed_category:
            out["category"] = guessed_category
    if not out.get("topic"):
        guessed_topic = _guess_topic(str(out.get("path") or path))
        if guessed_topic:
            out["topic"] = guessed_topic
    if not out.get("region"):
        guessed_region = _guess_region(str(out.get("path") or path))
        if guessed_region:
            out["region"] = guessed_region
    if not out.get("source_policy"):
        guessed_policy = _guess_source_policy(out)
        if guessed_policy:
            out["source_policy"] = guessed_policy
    return out
