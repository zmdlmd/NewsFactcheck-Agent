from __future__ import annotations

import re
from typing import Any, Dict, List

from app.agent.state import AgentState
from app.core.config import get_settings
from app.tools.claim_profile import build_claim_profile
from app.tools.fetch import fetch_page_text
from app.tools.retrieval import dedupe_sources, format_retrieval_diagnostics, retrieve_sources_detailed
from app.tools.search import score_source


_NUMERIC_CLAIM_RE = re.compile(
    r"(?:\d[\d,.:/%-]*|"
    r"\b(?:percent|percentage|million|billion|trillion|revenue|sales|budget|gdp|population|rate|share|price)\b|"
    r"(?:美元|美金|元|亿元|万亿|万人|万名|亿人|百分之|增长率|GDP|营收|票房|预算|人口|占比|比例))",
    re.IGNORECASE,
)
_TEMPORAL_CLAIM_RE = re.compile(
    r"(?:\b(?:today|current|currently|latest|recent|recently|new|newest|now|this year|this month|this week|"
    r"yesterday|tomorrow|announced|announcement|released|launch|won|elected|appointed|as of|quarter|q[1-4]|20\d{2})\b|"
    r"(?:今天|当前|目前|最新|最近|近日|今年|本月|本周|昨天|昨日|明天|刚刚|宣布|发布|任命|当选|截至|现任|季度|近年))",
    re.IGNORECASE,
)
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
    "报告",
    "数据",
    "统计",
    "年报",
    "公报",
    "白皮书",
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
    "新闻",
    "公告",
    "通报",
    "发布",
    "更新",
    "快讯",
    "最新",
)


def node_pro_search(state: AgentState) -> Dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    if not plan.get("run_pro", True):
        return {"logs": ["[pro_search] skipped"]}

    if state["search_budget_remaining"] <= 0:
        return {"logs": ["[pro_search] no budget"]}

    search_plan = state.get("pro_plan") or {}
    query = (search_plan.get("query") or "").strip()
    if not query:
        return {"logs": ["[pro_search] empty query"]}

    claim_text = _active_claim_text(state)
    state["search_budget_remaining"] -= 1
    res, diagnostics = retrieve_sources_detailed(
        query,
        claim_text=claim_text,
        include_domains=search_plan.get("include_domains"),
        exclude_domains=search_plan.get("exclude_domains"),
        max_results=5,
        rag_filters=search_plan.get("rag_filters"),
    )

    cid = state["active_claim_id"]
    claim_work = state["work"][cid]
    claim_work["pro_sources"] = dedupe_sources(claim_work["pro_sources"] + res)
    diagnostics_entry = {
        **diagnostics,
        "side": "pro",
        "claim_id": cid,
        "query": query,
    }
    logs = [f"[pro_search] +{len(res)} remaining={state['search_budget_remaining']}"]
    if get_settings().retrieval_diagnostics_enabled:
        logs.append(f"[pro_search.diagnostics] {format_retrieval_diagnostics(diagnostics)}")

    return {
        "work": state["work"],
        "search_budget_remaining": state["search_budget_remaining"],
        "retrieval_diagnostics": [diagnostics_entry],
        "logs": logs,
    }


def node_con_search(state: AgentState) -> Dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    if not plan.get("run_con", True):
        return {"logs": ["[con_search] skipped"]}

    if state["search_budget_remaining"] <= 0:
        return {"logs": ["[con_search] no budget"]}

    search_plan = state.get("con_plan") or {}
    query = (search_plan.get("query") or "").strip()
    if not query:
        return {"logs": ["[con_search] empty query"]}

    claim_text = _active_claim_text(state)
    state["search_budget_remaining"] -= 1
    res, diagnostics = retrieve_sources_detailed(
        query,
        claim_text=claim_text,
        include_domains=search_plan.get("include_domains"),
        exclude_domains=search_plan.get("exclude_domains"),
        max_results=5,
        rag_filters=search_plan.get("rag_filters"),
    )

    cid = state["active_claim_id"]
    claim_work = state["work"][cid]
    claim_work["con_sources"] = dedupe_sources(claim_work["con_sources"] + res)
    diagnostics_entry = {
        **diagnostics,
        "side": "con",
        "claim_id": cid,
        "query": query,
    }
    logs = [f"[con_search] +{len(res)} remaining={state['search_budget_remaining']}"]
    if get_settings().retrieval_diagnostics_enabled:
        logs.append(f"[con_search.diagnostics] {format_retrieval_diagnostics(diagnostics)}")

    return {
        "work": state["work"],
        "search_budget_remaining": state["search_budget_remaining"],
        "retrieval_diagnostics": [diagnostics_entry],
        "logs": logs,
    }


def _active_claim_text(state: AgentState) -> str:
    cid = state.get("active_claim_id")
    for claim in state.get("claims", []):
        if claim.get("id") == cid:
            return (claim.get("text") or "").strip()
    claim_index = state.get("claim_index", 0)
    claims = state.get("claims", [])
    if 0 <= claim_index < len(claims):
        return (claims[claim_index].get("text") or "").strip()
    return ""


def _claim_profile(claim_text: str) -> Dict[str, Any]:
    profile = build_claim_profile(claim_text)
    return {
        "numeric": bool(profile.get("numeric")),
        "temporal": bool(profile.get("temporal")),
        "years": set(profile.get("years") or []),
    }


def _fetch_candidate_score(source: Dict[str, Any], claim_profile: Dict[str, Any]) -> int:
    score = score_source(source)
    url = (source.get("url") or "").lower()
    title = (source.get("title") or "").lower()
    snippet = (source.get("snippet") or "").lower()
    text_blob = " ".join(part for part in [url, title, snippet] if part)

    if claim_profile.get("numeric"):
        if any(token in text_blob for token in _NUMERIC_SOURCE_HINTS):
            score += 10
        if url.endswith(".pdf"):
            score += 4
        if any(year in text_blob for year in claim_profile.get("years", set())):
            score += 3

    if claim_profile.get("temporal"):
        if any(token in text_blob for token in _TEMPORAL_SOURCE_HINTS):
            score += 9
        if any(year in text_blob for year in claim_profile.get("years", set())):
            score += 4
        if claim_profile.get("temporal") and not claim_profile.get("numeric") and url.endswith(".pdf"):
            score -= 3

    return score


def _rank_fetch_candidates(sources: List[Dict[str, Any]], claim_profile: Dict[str, Any]) -> List[tuple[int, int, str]]:
    ranked: List[tuple[int, int, str]] = []
    seen_urls = set()
    for index, source in enumerate(sources):
        url = (source.get("url") or "").strip()
        if not url or source.get("page_fetch_attempted") or source.get("source_type") == "rag":
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        score = _fetch_candidate_score(source, claim_profile)
        score -= index
        ranked.append((score, index, url))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return ranked


def _select_fetch_targets(claim_work: Dict[str, Any], budget: int, claim_text: str) -> List[str]:
    claim_profile = _claim_profile(claim_text)
    per_side_ranked: Dict[str, List[tuple[int, int, str]]] = {
        "pro_sources": _rank_fetch_candidates(claim_work.get("pro_sources", []), claim_profile),
        "con_sources": _rank_fetch_candidates(claim_work.get("con_sources", []), claim_profile),
    }

    primary_candidates: List[tuple[int, int, str]] = []
    overflow_candidates: List[tuple[int, int, str]] = []
    for side_order, key in enumerate(["pro_sources", "con_sources"]):
        ranked = per_side_ranked[key]
        for candidate_index, (score, _, url) in enumerate(ranked):
            row = (score, side_order, url)
            if candidate_index == 0:
                primary_candidates.append(row)
            else:
                overflow_candidates.append(row)

    primary_candidates.sort(key=lambda row: (-row[0], row[1]))
    overflow_candidates.sort(key=lambda row: (-row[0], row[1]))

    selected: List[str] = []
    seen_urls = set()
    for _, _, url in primary_candidates + overflow_candidates:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        selected.append(url)
        if len(selected) >= budget:
            break
    return selected


def node_fetch_key_pages(state: AgentState) -> Dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    if not (state["enable_fetch"] and plan.get("use_fetch")):
        return {"logs": ["[fetch] disabled"]}

    if state["fetch_budget_remaining"] <= 0:
        return {"logs": ["[fetch] no budget"]}

    cid = state["active_claim_id"]
    claim_work = state["work"][cid]
    claim_text = _active_claim_text(state)
    targets = _select_fetch_targets(claim_work, state["fetch_budget_remaining"], claim_text)

    attempted = 0
    accepted = 0
    for url in targets:
        if state["fetch_budget_remaining"] <= 0:
            break
        text = fetch_page_text(url)
        state["fetch_budget_remaining"] -= 1
        attempted += 1
        for key in ["pro_sources", "con_sources"]:
            for source in claim_work[key]:
                if source.get("url") == url:
                    source["page_fetch_attempted"] = True
                    source["page_text"] = text
        if text:
            accepted += 1

    return {
        "work": state["work"],
        "fetch_budget_remaining": state["fetch_budget_remaining"],
        "logs": [f"[fetch] attempted={attempted} accepted={accepted} remaining_fetch={state['fetch_budget_remaining']}"],
    }
