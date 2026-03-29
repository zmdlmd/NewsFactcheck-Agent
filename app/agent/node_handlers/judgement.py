from __future__ import annotations

from typing import Any, Dict

from app.agent.llm import build_model, invoke_structured
from app.agent.models import Judgement
from app.agent.prompts.judgement import judgement_system_prompt, judgement_user_prompt
from app.agent.state import AgentState


def node_judge(state: AgentState) -> Dict[str, Any]:
    model = build_model(
        state["_model_name"],
        state.get("_llm_base_url"),
        state.get("_llm_api_key"),
    )
    cid = state["active_claim_id"]
    claim_map = {claim["id"]: claim for claim in state["claims"]}
    claim_text = claim_map[cid]["text"]
    claim_work = state["work"][cid]

    sys = judgement_system_prompt()
    user = judgement_user_prompt(
        claim_text,
        claim_work["pro_sources"],
        claim_work["con_sources"],
    )

    out: Judgement = invoke_structured(model, Judgement, sys, user)
    judgement = out.model_dump()

    if not judgement.get("best_sources"):
        pool = (claim_work.get("pro_sources") or []) + (claim_work.get("con_sources") or [])
        seen = set()
        best = []
        for source in pool:
            url = source.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            best.append(
                {
                    "title": source.get("title", ""),
                    "url": url,
                    "snippet": source.get("snippet", ""),
                    "page_text": source.get("page_text"),
                }
            )
            if len(best) >= 3:
                break
        judgement["best_sources"] = best

    claim_work["judgement"] = judgement
    claim_work["rounds"] += 1

    return {
        "work": state["work"],
        "logs": [f"[judge] {out.verdict} conf={out.confidence:.2f} rounds={claim_work['rounds']}"],
    }
