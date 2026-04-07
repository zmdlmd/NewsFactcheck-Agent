from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field

from app.agent.llm import build_model, invoke_structured
from app.core.config import get_settings
from app.tools.claim_profile import build_claim_profile, detect_text_language
from app.tools.rag import rag_search
from app.tools.search import score_source, tavily_search
from app.tools.taxonomy import format_rag_filters, normalize_rag_filters, normalize_taxonomy_metadata

_NUMERIC_SOURCE_HINTS = (
    "report",
    "data",
    "dataset",
    "statistics",
    "statistical",
    "factsheet",
    "fact-sheet",
    "annual",
    "census",
    "budget",
    "table",
    "appendix",
    "pdf",
    "revenue",
    "population",
    "gdp",
    "income",
    "earnings",
    "finance",
)

_TEMPORAL_SOURCE_HINTS = (
    "news",
    "press",
    "release",
    "releases",
    "latest",
    "update",
    "updates",
    "announcement",
    "announcements",
    "today",
    "current",
    "live",
    "blog",
    "newsroom",
    "bulletin",
    "statement",
)

_OVERLAP_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "about",
    "claim",
    "reported",
    "report",
    "according",
    "official",
    "said",
}


class _LLMRerankOutput(BaseModel):
    ordered_ids: list[str] = Field(default_factory=list)


def _canonical_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme:
        return ""
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def _metadata_values(metadata: dict[str, Any], key: str) -> list[str]:
    raw = metadata.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip().lower() for item in raw if str(item).strip()]
    return [str(raw).strip().lower()] if str(raw).strip() else []


def _primary_metadata_value(metadata: dict[str, Any], key: str) -> str:
    values = _metadata_values(metadata, key)
    return values[0] if values else ""


def _metadata_has_any(metadata: dict[str, Any], key: str, candidates: set[str]) -> bool:
    return bool(set(_metadata_values(metadata, key)) & candidates)


def _normalize_source(item: dict[str, Any]) -> dict[str, Any]:
    source_type = (item.get("source_type") or "web").strip().lower()
    normalized = dict(item)
    normalized["source_type"] = "rag" if source_type == "rag" else "web"
    normalized["title"] = (normalized.get("title") or "").strip()
    normalized["snippet"] = (normalized.get("snippet") or "").strip()
    normalized["source_name"] = (normalized.get("source_name") or "").strip() or None
    normalized["doc_id"] = (normalized.get("doc_id") or "").strip() or None
    normalized["chunk_id"] = (normalized.get("chunk_id") or "").strip() or None
    normalized["url"] = _canonical_url(normalized.get("url", ""))
    metadata = dict(normalized.get("metadata") or {})
    if normalized["source_type"] == "web" and normalized["url"] and "origin_url" not in metadata:
        metadata["origin_url"] = normalized["url"]
    normalized["metadata"] = normalize_taxonomy_metadata(
        metadata,
        title=normalized["title"],
        source_name=normalized.get("source_name") or "",
        path=str(metadata.get("path") or ""),
    )
    normalized["page_text"] = normalized.get("page_text")
    normalized["score"] = normalized.get("score")
    if normalized["source_type"] == "web" and not normalized.get("source_name") and normalized["url"]:
        normalized["source_name"] = _domain_from_url(normalized["url"]) or None
    return normalized


def _metadata_blob(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    parts: list[str] = []
    for value in metadata.values():
        if isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, (str, int, float)):
            parts.append(str(value))
    return " ".join(parts)


def _source_text_blob(item: dict[str, Any]) -> str:
    normalized = _normalize_source(item)
    return " ".join(
        part
        for part in [
            normalized.get("title") or "",
            normalized.get("snippet") or "",
            (normalized.get("page_text") or "")[:800],
            normalized.get("url") or "",
            normalized.get("source_name") or "",
            _metadata_blob(normalized),
        ]
        if part
    ).lower()


def _tokenize_overlap_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
        if token not in _OVERLAP_STOPWORDS
    }


def _lexical_overlap_bonus(query_text: str | None, item: dict[str, Any]) -> float:
    if not query_text:
        return 0.0
    query_terms = _tokenize_overlap_terms(query_text)
    if not query_terms:
        return 0.0
    source_terms = _tokenize_overlap_terms(_source_text_blob(item))
    if not source_terms:
        return 0.0
    overlap = len(query_terms & source_terms)
    if overlap <= 0:
        return 0.0
    return (overlap / max(1, len(query_terms))) * 14


def _taxonomy_quality_bonus(item: dict[str, Any]) -> float:
    normalized = _normalize_source(item)
    metadata = normalized.get("metadata") or {}
    score = 0.0

    source_policy = _primary_metadata_value(metadata, "source_policy")
    if source_policy == "official":
        score += 6
    elif source_policy == "institutional":
        score += 4
    elif source_policy == "academic":
        score += 3
    elif source_policy == "media":
        score += 1.5
    elif source_policy == "reference":
        score += 1
    elif source_policy == "community":
        score -= 2

    if metadata.get("institution"):
        score += 1
    if metadata.get("topic"):
        score += 0.5
    if metadata.get("region"):
        score += 0.5
    if _metadata_has_any(metadata, "category", {"report", "data", "announcement", "news", "policy", "research", "reference"}):
        score += 1
    return score


def _normalize_web_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        url = _canonical_url(item.get("url", ""))
        if not url:
            continue
        out.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": url,
                "snippet": (item.get("snippet") or "").strip(),
                "page_text": item.get("page_text"),
                "source_type": "web",
                "source_name": _domain_from_url(url) or None,
                "doc_id": None,
                "chunk_id": None,
                "score": None,
                "metadata": {},
            }
        )
    return out


def _source_key(item: dict[str, Any]) -> str:
    normalized = _normalize_source(item)
    if normalized["source_type"] == "rag":
        return f"rag::{normalized.get('doc_id') or ''}::{normalized.get('chunk_id') or ''}::{normalized.get('url') or ''}"
    return f"web::{normalized.get('url') or ''}"


def _merge_source(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for field in ["title", "snippet", "page_text", "source_name", "doc_id", "chunk_id"]:
        if not merged.get(field) and candidate.get(field):
            merged[field] = candidate[field]
    if merged.get("score") is None and candidate.get("score") is not None:
        merged["score"] = candidate["score"]
    elif merged.get("score") is not None and candidate.get("score") is not None:
        merged["score"] = max(float(merged["score"]), float(candidate["score"]))
    if candidate.get("metadata"):
        merged["metadata"] = {**merged.get("metadata", {}), **candidate["metadata"]}
    return merged


def dedupe_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        normalized = _normalize_source(item)
        if not normalized.get("url"):
            continue
        key = _source_key(normalized)
        if key in seen:
            seen[key] = _merge_source(seen[key], normalized)
            continue
        seen[key] = normalized
        order.append(key)
    return [seen[key] for key in order]


def _claim_aware_bonus(item: dict[str, Any], claim_text: str | None) -> float:
    if not claim_text:
        return 0.0

    profile = build_claim_profile(claim_text)
    blob = _source_text_blob(item)
    normalized = _normalize_source(item)
    metadata = normalized.get("metadata") or {}
    score = 0.0

    if profile.get("numeric"):
        if any(token in blob for token in _NUMERIC_SOURCE_HINTS):
            score += 10
        if any(year in blob for year in profile.get("years") or []):
            score += 3
        if normalized.get("url", "").lower().endswith(".pdf"):
            score += 3
        if _metadata_has_any(metadata, "category", {"report", "data", "statistics", "dataset"}):
            score += 6

    if profile.get("temporal"):
        if any(token in blob for token in _TEMPORAL_SOURCE_HINTS):
            score += 10
        if any(year in blob for year in profile.get("years") or []):
            score += 4
        if _metadata_has_any(metadata, "category", {"news", "update", "announcement", "press"}):
            score += 6
        if profile.get("temporal") and not profile.get("numeric") and normalized.get("url", "").lower().endswith(".pdf"):
            score -= 3

    claim_language = profile.get("language")
    source_language = _primary_metadata_value(metadata, "lang") or _primary_metadata_value(metadata, "language") or detect_text_language(blob)
    source_language = source_language.lower()
    if claim_language in {"zh", "en"} and source_language == claim_language:
        score += 4
    elif claim_language in {"zh", "en"} and source_language not in {claim_language, "mixed", "unknown"}:
        score -= 2

    return score


def _base_score(item: dict[str, Any], include_domains: list[str] | None = None) -> float:
    normalized = _normalize_source(item)
    if normalized["source_type"] == "rag":
        score = float(normalized.get("score") or 0.0) * 40
        if normalized.get("page_text"):
            score += 6
        if normalized.get("source_name"):
            score += 2
        if normalized.get("title"):
            score += 1
        return score
    return float(score_source(normalized, include_domains=include_domains))


def _score_row(
    item: dict[str, Any],
    *,
    include_domains: list[str] | None = None,
    claim_text: str | None = None,
    source_index: int | None = None,
) -> dict[str, Any]:
    normalized = _normalize_source(item)
    base = _base_score(normalized, include_domains=include_domains)
    lexical = _lexical_overlap_bonus(claim_text, normalized)
    taxonomy = _taxonomy_quality_bonus(normalized)
    claim = _claim_aware_bonus(normalized, claim_text)
    total = base + lexical + taxonomy + claim
    return {
        "item": normalized,
        "source_index": source_index,
        "base_score": base,
        "lexical_bonus": lexical,
        "taxonomy_bonus": taxonomy,
        "claim_bonus": claim,
        "total_score": total,
        "adjusted_score": total,
    }


def _source_domain(item: dict[str, Any]) -> str:
    normalized = _normalize_source(item)
    if normalized["source_type"] == "web":
        return _domain_from_url(normalized.get("url") or "")
    metadata = normalized.get("metadata") or {}
    origin_url = _primary_metadata_value(metadata, "origin_url")
    if origin_url:
        return _domain_from_url(origin_url)
    return (normalized.get("source_name") or "").lower()


def _diversity_penalty(candidate: dict[str, Any], selected: list[dict[str, Any]]) -> float:
    if not selected:
        return 0.0

    candidate_item = candidate["item"]
    candidate_metadata = candidate_item.get("metadata") or {}
    candidate_source_name = (candidate_item.get("source_name") or "").lower()
    candidate_domain = _source_domain(candidate_item)
    candidate_category = _primary_metadata_value(candidate_metadata, "category")
    candidate_policy = _primary_metadata_value(candidate_metadata, "source_policy")
    penalty = 0.0

    for existing in selected:
        existing_item = existing["item"]
        existing_metadata = existing_item.get("metadata") or {}
        if candidate_item.get("source_type") == existing_item.get("source_type"):
            penalty += 0.05
        if candidate_source_name and candidate_source_name == (existing_item.get("source_name") or "").lower():
            penalty += 0.35
        if candidate_domain and candidate_domain == _source_domain(existing_item):
            penalty += 0.25
        if candidate_category and candidate_category == _primary_metadata_value(existing_metadata, "category"):
            penalty += 0.12
        if candidate_policy and candidate_policy == _primary_metadata_value(existing_metadata, "source_policy"):
            penalty += 0.08
    return penalty


def _apply_diversity_rerank(
    scored_rows: list[dict[str, Any]],
    *,
    max_results: int,
    rerank_max_candidates: int,
    diversity_weight: float,
) -> tuple[list[dict[str, Any]], bool]:
    if len(scored_rows) <= 1:
        return scored_rows[:max_results], False

    pool_size = min(len(scored_rows), max(max_results, rerank_max_candidates))
    pool = [dict(row) for row in scored_rows[:pool_size]]
    selected: list[dict[str, Any]] = []

    while pool and len(selected) < max_results:
        best_index = 0
        best_adjusted = None
        best_total = None
        for index, row in enumerate(pool):
            penalty = _diversity_penalty(row, selected)
            adjusted = row["total_score"] - (penalty * diversity_weight)
            if (
                best_adjusted is None
                or adjusted > best_adjusted
                or (adjusted == best_adjusted and row["total_score"] > (best_total or 0.0))
            ):
                best_index = index
                best_adjusted = adjusted
                best_total = row["total_score"]
        chosen = pool.pop(best_index)
        chosen["adjusted_score"] = float(best_adjusted if best_adjusted is not None else chosen["total_score"])
        selected.append(chosen)

    if len(selected) < max_results:
        for row in scored_rows[pool_size:]:
            if len(selected) >= max_results:
                break
            selected.append(row)

    return selected[:max_results], True


def _diagnostic_entry(rank: int, row: dict[str, Any]) -> dict[str, Any]:
    item = row["item"]
    metadata = item.get("metadata") or {}
    return {
        "rank": rank,
        "source_type": item.get("source_type"),
        "title": item.get("title"),
        "url": item.get("url"),
        "source_name": item.get("source_name"),
        "category": _primary_metadata_value(metadata, "category") or None,
        "source_policy": _primary_metadata_value(metadata, "source_policy") or None,
        "base_score": round(float(row["base_score"]), 3),
        "lexical_bonus": round(float(row["lexical_bonus"]), 3),
        "taxonomy_bonus": round(float(row["taxonomy_bonus"]), 3),
        "claim_bonus": round(float(row["claim_bonus"]), 3),
        "total_score": round(float(row["total_score"]), 3),
        "adjusted_score": round(float(row["adjusted_score"]), 3),
    }


def _llm_rerank_system_prompt() -> str:
    return (
        "You are a retrieval reranker for evidence selection.\n"
        "Reorder the candidate IDs from most useful to least useful for fact-checking the claim.\n"
        "Prefer authoritative, directly relevant, non-redundant evidence.\n"
        "Return only structured output."
    )


def _llm_rerank_user_prompt(claim_text: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"Claim: {claim_text}", "Candidates:"]
    for row in rows:
        item = row["item"]
        metadata = item.get("metadata") or {}
        lines.extend(
            [
                f"- id: {row['candidate_id']}",
                f"  source_type: {item.get('source_type')}",
                f"  title: {item.get('title')}",
                f"  source_name: {item.get('source_name')}",
                f"  category: {_primary_metadata_value(metadata, 'category') or 'unknown'}",
                f"  source_policy: {_primary_metadata_value(metadata, 'source_policy') or 'unknown'}",
                f"  snippet: {(item.get('snippet') or '')[:260]}",
            ]
        )
    lines.append("Return ordered_ids using only the candidate ids above.")
    return "\n".join(lines)


def _apply_llm_rerank(
    scored_rows: list[dict[str, Any]],
    *,
    claim_text: str | None,
    max_results: int,
    rerank_max_candidates: int,
) -> tuple[list[dict[str, Any]], bool]:
    if not claim_text or len(scored_rows) <= 1:
        return scored_rows[:max_results], False

    settings = get_settings()
    pool_size = min(len(scored_rows), max(max_results, rerank_max_candidates))
    pool: list[dict[str, Any]] = []
    for index, row in enumerate(scored_rows[:pool_size], start=1):
        candidate = dict(row)
        candidate["candidate_id"] = f"c{candidate.get('source_index') or index}"
        pool.append(candidate)

    model = build_model(settings.model_name, settings.llm_base_url, settings.llm_api_key)
    out: _LLMRerankOutput = invoke_structured(
        model,
        _LLMRerankOutput,
        _llm_rerank_system_prompt(),
        _llm_rerank_user_prompt(claim_text, pool),
    )

    by_id = {row["candidate_id"]: row for row in pool}
    ordered: list[dict[str, Any]] = []
    seen = set()
    for candidate_id in out.ordered_ids:
        row = by_id.get(candidate_id)
        if row is None or candidate_id in seen:
            continue
        seen.add(candidate_id)
        ordered.append(row)
    for row in pool:
        if row["candidate_id"] in seen:
            continue
        ordered.append(row)

    total = len(ordered)
    for index, row in enumerate(ordered, start=1):
        row["adjusted_score"] = row["total_score"] + ((total - index + 1) * 0.5)
    if len(ordered) < max_results:
        ordered.extend(scored_rows[pool_size:max_results])
    return ordered[:max_results], True


def format_retrieval_diagnostics(diagnostics: dict[str, Any]) -> str:
    counts = diagnostics.get("counts") or {}
    filters = diagnostics.get("rag_filters") or {}
    return (
        f"mode={diagnostics.get('mode')} "
        f"rag={counts.get('rag', 0)} "
        f"web={counts.get('web', 0)} "
        f"merged={counts.get('merged', 0)} "
        f"returned={counts.get('returned', 0)} "
        f"rerank={diagnostics.get('rerank_mode')} "
        f"used_rerank={diagnostics.get('used_rerank', False)} "
        f"filters={format_rag_filters(filters)}"
    )


def search_web(
    query: str,
    *,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    return _normalize_web_sources(
        tavily_search(
            query,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            max_results=max_results,
        )
    )


def search_rag(
    query: str,
    *,
    max_results: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return dedupe_sources(rag_search(query, top_k=max_results, filters=filters))


def retrieve_sources_detailed(
    query: str,
    *,
    mode: str | None = None,
    claim_text: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 5,
    rag_filters: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = get_settings()
    retrieval_mode = (mode or settings.retrieval_mode or "web").strip().lower()
    normalized_filters = normalize_rag_filters(rag_filters)

    diagnostics: dict[str, Any] = {
        "mode": retrieval_mode,
        "rag_filters": normalized_filters,
        "rerank_mode": settings.rerank_mode,
        "used_rerank": False,
        "counts": {"rag": 0, "web": 0, "merged": 0, "returned": 0},
        "top_results": [],
    }

    web_results: list[dict[str, Any]] = []
    rag_results: list[dict[str, Any]] = []

    if retrieval_mode == "web":
        web_results = dedupe_sources(
            search_web(
                query,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                max_results=max_results,
            )
        )
        merged = web_results
    elif retrieval_mode == "rag":
        rag_results = search_rag(query, max_results=max_results, filters=normalized_filters)
        merged = rag_results
    elif retrieval_mode == "hybrid":
        try:
            rag_results = search_rag(
                query,
                max_results=min(max_results, max(1, settings.rag_top_k)),
                filters=normalized_filters,
            )
        except Exception as exc:
            diagnostics["rag_error"] = exc.__class__.__name__
            rag_results = []
        web_results = search_web(
            query,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            max_results=max_results,
        )
        merged = dedupe_sources(rag_results + web_results)
    else:
        raise ValueError(f"Unsupported retrieval mode: {retrieval_mode}")

    diagnostics["counts"]["rag"] = len(rag_results)
    diagnostics["counts"]["web"] = len(web_results)
    diagnostics["counts"]["merged"] = len(merged)

    scored_rows = [
        _score_row(
            item,
            include_domains=include_domains,
            claim_text=claim_text or query,
            source_index=index,
        )
        for index, item in enumerate(merged, start=1)
    ]
    scored_rows.sort(
        key=lambda row: (
            -row["total_score"],
            row["item"].get("title") or "",
            row["item"].get("url") or "",
        )
    )

    rerank_mode = (settings.rerank_mode or "off").strip().lower()
    if rerank_mode == "diversity":
        selected_rows, used_rerank = _apply_diversity_rerank(
            scored_rows,
            max_results=max_results,
            rerank_max_candidates=settings.rerank_max_candidates,
            diversity_weight=settings.rerank_diversity_weight,
        )
        diagnostics["used_rerank"] = used_rerank
    elif rerank_mode == "llm":
        try:
            selected_rows, used_rerank = _apply_llm_rerank(
                scored_rows,
                claim_text=claim_text or query,
                max_results=max_results,
                rerank_max_candidates=settings.rerank_max_candidates,
            )
            diagnostics["used_rerank"] = used_rerank
        except Exception as exc:
            diagnostics["llm_rerank_error"] = exc.__class__.__name__
            selected_rows = scored_rows[:max_results]
    else:
        selected_rows = scored_rows[:max_results]

    results = [row["item"] for row in selected_rows[:max_results]]
    diagnostics["counts"]["returned"] = len(results)
    if settings.retrieval_diagnostics_enabled:
        diagnostics["top_results"] = [
            _diagnostic_entry(index, row)
            for index, row in enumerate(selected_rows[: min(3, len(selected_rows))], start=1)
        ]

    return results, diagnostics


def retrieve_sources(
    query: str,
    *,
    mode: str | None = None,
    claim_text: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 5,
    rag_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results, _ = retrieve_sources_detailed(
        query,
        mode=mode,
        claim_text=claim_text,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        max_results=max_results,
        rag_filters=rag_filters,
    )
    return results
