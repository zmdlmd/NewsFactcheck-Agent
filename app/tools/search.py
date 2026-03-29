from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse

from langchain_tavily import TavilySearch

from app.core.config import get_settings

_CACHE_LOCK = threading.Lock()
_HIGH_TRUST_HOSTS = {
    "nasa.gov",
    "esa.int",
    "who.int",
    "cdc.gov",
    "nih.gov",
    "un.org",
    "ipcc.ch",
    "noaa.gov",
    "iep.org",
    "britannica.com",
}
_LOW_TRUST_HOSTS = {
    "wikipedia.org",
    "baike.baidu.com",
    "fandom.com",
    "reddit.com",
    "quora.com",
    "medium.com",
}
_LOW_TRUST_PATH_MARKERS = ("/wiki/", "/item/", "/question/", "/answers/")


def _parse_any(output: Any) -> Dict[str, Any]:
    if output is None:
        return {"results": []}
    if hasattr(output, "content"):
        try:
            return json.loads(output.content)
        except Exception:
            return {"results": []}
    if isinstance(output, str):
        try:
            return json.loads(output)
        except Exception:
            return {"results": []}
    if isinstance(output, dict):
        return output
    return {"results": []}


def _canonical_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.netloc:
        return ""
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def _matches_domain(domain: str, candidates: list[str] | None) -> bool:
    if not domain or not candidates:
        return False
    for candidate in candidates:
        candidate = candidate.lower().strip()
        if not candidate:
            continue
        if domain == candidate or domain.endswith(f".{candidate}"):
            return True
    return False


def _authority_score(domain: str, url: str, snippet: str, include_domains: list[str] | None) -> int:
    score = 0
    lowered_url = url.lower()
    lowered_snippet = snippet.lower()

    if _matches_domain(domain, include_domains):
        score += 40
    if domain.endswith((".gov", ".edu", ".mil", ".int")) or ".gov." in domain or ".edu." in domain:
        score += 28
    if _matches_domain(domain, list(_HIGH_TRUST_HOSTS)):
        score += 18
    if _matches_domain(domain, list(_LOW_TRUST_HOSTS)):
        score -= 18
    if any(marker in lowered_url for marker in _LOW_TRUST_PATH_MARKERS):
        score -= 6
    if lowered_url.endswith(".pdf"):
        score += 3 if score > 0 else -2
    if len(snippet) >= 180:
        score += 4
    elif len(snippet) >= 80:
        score += 2
    if any(token in lowered_snippet for token in ("official", "study", "report", "university", "government", "nasa", "who", "british")):
        score += 2
    return score


def score_source(item: Dict[str, Any], include_domains: list[str] | None = None) -> int:
    url = _canonical_url((item.get("url") or "").strip())
    if not url:
        return -1000

    snippet = (item.get("snippet") or "").strip()
    title = (item.get("title") or "").strip()
    domain = _domain_from_url(url)
    score = _authority_score(domain, url, snippet, include_domains)
    if title:
        score += min(len(title), 120) // 30
    if len(snippet) >= 240:
        score += 3
    elif len(snippet) >= 120:
        score += 1
    return score


def normalize_results(raw: Dict[str, Any], max_keep: int | None = 5) -> List[Dict[str, str]]:
    results = raw.get("results", []) or []
    cleaned: List[Dict[str, str]] = []
    slice_end = max_keep if max_keep is not None else len(results)
    for r in results[:slice_end]:
        url = _canonical_url((r.get("url") or "").strip())
        if not url:
            continue
        cleaned.append(
            {
                "title": (r.get("title") or "").strip(),
                "url": url,
                "snippet": (r.get("content") or r.get("snippet") or "").strip(),
            }
        )
    return cleaned


def dedupe_by_url(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for it in items:
        url = _canonical_url(it.get("url", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned = dict(it)
        cleaned["url"] = url
        out.append(cleaned)
    return out


def _rank_results(
    items: List[Dict[str, str]],
    *,
    include_domains: list[str] | None,
    max_keep: int,
) -> List[Dict[str, str]]:
    enriched = []
    for index, item in enumerate(dedupe_by_url(items)):
        domain = _domain_from_url(item["url"])
        score = score_source(item, include_domains=include_domains)
        enriched.append((score, index, domain, item))

    enriched.sort(key=lambda row: (-row[0], row[1]))

    selected: List[Dict[str, str]] = []
    leftovers: List[Dict[str, str]] = []
    seen_domains = set()
    for _, _, domain, item in enriched:
        if domain and domain not in seen_domains:
            selected.append(item)
            seen_domains.add(domain)
        else:
            leftovers.append(item)
        if len(selected) >= max_keep:
            break

    if len(selected) < max_keep:
        for item in leftovers:
            if len(selected) >= max_keep:
                break
            selected.append(item)
    return selected[:max_keep]


def _cache_dir() -> str:
    settings = get_settings()
    path = os.path.join(settings.data_dir, "cache", "search")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_key(
    query: str,
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
    max_results: int,
) -> str:
    payload = {
        "query": query.strip(),
        "include_domains": sorted((include_domains or [])),
        "exclude_domains": sorted((exclude_domains or [])),
        "max_results": max_results,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_path(cache_key: str) -> str:
    return os.path.join(_cache_dir(), f"{cache_key}.json")


def _load_cached_results(cache_key: str) -> List[Dict[str, str]] | None:
    settings = get_settings()
    if not settings.search_cache_enabled:
        return None

    path = _cache_path(cache_key)
    if not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    created_at = float(payload.get("created_at", 0))
    if settings.search_cache_ttl_seconds > 0 and (time.time() - created_at) > settings.search_cache_ttl_seconds:
        return None
    return dedupe_by_url(payload.get("results") or [])


def _save_cached_results(cache_key: str, results: List[Dict[str, str]]) -> None:
    settings = get_settings()
    if not settings.search_cache_enabled:
        return

    path = _cache_path(cache_key)
    payload = {"created_at": time.time(), "results": results}
    with _CACHE_LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def tavily_search(query: str, include_domains=None, exclude_domains=None, max_results: int = 5) -> List[Dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []

    cache_key = _cache_key(query, include_domains, exclude_domains, max_results)
    cached = _load_cached_results(cache_key)
    if cached is not None:
        return cached[:max_results]

    raw_fetch_count = min(max(max_results * 3, max_results), 10)
    tool = TavilySearch(max_results=raw_fetch_count, topic="general")
    args: Dict[str, Any] = {"query": query}
    if include_domains:
        args["include_domains"] = include_domains
    if exclude_domains:
        args["exclude_domains"] = exclude_domains

    raw = _parse_any(tool.invoke(args))
    cleaned = normalize_results(raw, max_keep=raw_fetch_count)
    ranked = _rank_results(cleaned, include_domains=include_domains, max_keep=max_results)
    _save_cached_results(cache_key, ranked)
    return ranked
