from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.llm import build_model, invoke_structured
from app.agent.models import FinalReport
from app.agent.prompts.reporting import (
    final_report_system_prompt,
    final_report_user_prompt,
    rewrite_summary_system_prompt,
    rewrite_summary_user_prompt,
)
from app.agent.render import render_markdown
from app.agent.state import AgentState, ClaimWork


def _clip(s: str | None, n: int = 800) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "..."


def _thin_sources(sources: List[Dict[str, Any]], k: int = 3) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for source in (sources or [])[:k]:
        out.append(
            {
                "title": _clip(source.get("title"), 200),
                "url": (source.get("url") or "").strip(),
                "snippet": _clip(source.get("snippet"), 600),
                "page_text": _clip(source.get("page_text"), 1000) if source.get("page_text") else None,
            }
        )
    return out


def _pick_fallback_sources(claim_work: ClaimWork, k: int = 3) -> List[Dict[str, Any]]:
    pool = (claim_work.get("pro_sources") or []) + (claim_work.get("con_sources") or [])
    seen = set()
    out: List[Dict[str, Any]] = []
    for source in pool:
        url = (source.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "title": source.get("title", ""),
                "url": url,
                "snippet": source.get("snippet", ""),
                "page_text": source.get("page_text"),
            }
        )
        if len(out) >= k:
            break
    return out


def _rewrite_summary_if_number_inconsistent(
    model: ChatOpenAI,
    claim_text: str,
    verdict: str,
    summary: str,
    sources: List[Dict[str, Any]],
) -> str:
    sys = rewrite_summary_system_prompt()
    user = rewrite_summary_user_prompt(claim_text, verdict, summary, sources)
    try:
        resp = model.invoke([SystemMessage(content=sys), HumanMessage(content=user)])
        text = getattr(resp, "content", "") or ""
        return text.strip() or summary
    except Exception:
        return summary


def node_write_report(state: AgentState) -> Dict[str, Any]:
    model = build_model(
        state["_model_name"],
        state.get("_llm_base_url"),
        state.get("_llm_api_key"),
    )
    claims = state.get("claims", [])
    work = state.get("work", {})
    sys = final_report_system_prompt()

    pack = []
    for claim in claims:
        cid = claim["id"]
        claim_work = work.get(cid)
        if not claim_work:
            continue

        judgement = claim_work.get("judgement") or {}
        best_sources = judgement.get("best_sources") or []
        fallback_sources = _pick_fallback_sources(claim_work, k=3)
        sources_for_report = best_sources or fallback_sources

        pack.append(
            {
                "claim_id": cid,
                "claim": claim["text"],
                "judgement": judgement,
                "sources_for_report": _thin_sources(sources_for_report, k=3),
                "pro_sources": _thin_sources(claim_work.get("pro_sources", []), k=3),
                "con_sources": _thin_sources(claim_work.get("con_sources", []), k=3),
            }
        )

    user = final_report_user_prompt(pack)

    out = None
    last_err: Optional[Exception] = None
    for _ in range(2):
        try:
            out = invoke_structured(model, FinalReport, sys, user)
            break
        except Exception as exc:
            last_err = exc
            user = user[:12000]

    if out is None:
        resp = model.invoke([SystemMessage(content=sys), HumanMessage(content=user)])
        md = (getattr(resp, "content", "") or "").strip()
        return {
            "final_report": {
                "overall_summary": "结构化报告生成失败，已降级为纯文本报告（请查看 final_markdown）。",
                "claims": [],
            },
            "final_markdown": md,
            "logs": [f"[write_report] structured failed -> markdown fallback | err={last_err}"],
        }

    report = out.model_dump()

    for item in report.get("claims", []) or []:
        cid = item.get("claim_id")
        if not cid or cid not in work:
            continue
        claim_work = work[cid]
        if not item.get("sources"):
            item["sources"] = _pick_fallback_sources(claim_work, k=3)

        item["summary"] = _rewrite_summary_if_number_inconsistent(
            model=model,
            claim_text=item.get("claim", ""),
            verdict=item.get("verdict", ""),
            summary=item.get("summary", "") or "",
            sources=item.get("sources", []) or [],
        )

    md = render_markdown(report)
    return {"final_report": report, "final_markdown": md, "logs": ["[write_report] done"]}
