from __future__ import annotations

import re
from typing import Any, Dict, List

from app.agent.llm import build_model, invoke_structured
from app.agent.models import ClaimsOutput, SearchPlan, SupervisorPlan
from app.agent.prompts.planning import (
    extract_claims_system_prompt,
    extract_claims_user_prompt,
    planner_system_prompt,
    planner_user_prompt,
    supervisor_system_prompt,
    supervisor_user_prompt,
)
from app.agent.state import AgentState, ClaimWork


_INPUT_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"请核查|核查|事实核查|帮我核查|验证一下|验证|核实|"
    r"fact[- ]?check(?: this claim)?|check(?: this claim)?|verify(?: this claim)?"
    r")\s*[:：]?\s*",
    re.IGNORECASE,
)
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)、])\s*")


def _dedupe_list(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        x = (x or "").strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _normalize_claim_text(text: str | None) -> str:
    text = (text or "").strip()
    text = _INPUT_PREFIX_RE.sub("", text)
    text = text.strip(" \t\r\n\"'“”‘’[]()（）")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fallback_claims_from_input(input_text: str, max_claims: int) -> List[Dict[str, Any]]:
    candidates: List[str] = []
    for line in input_text.splitlines():
        line = _BULLET_PREFIX_RE.sub("", line).strip()
        line = _normalize_claim_text(line)
        if line:
            candidates.append(line)

    if not candidates:
        whole = _normalize_claim_text(input_text)
        if whole:
            candidates.append(whole)

    claims: List[Dict[str, Any]] = []
    seen = set()
    for text in candidates:
        if text in seen:
            continue
        seen.add(text)
        claims.append(
            {
                "text": text,
                "search_hint": text,
            }
        )
        if len(claims) >= max_claims:
            break
    return claims


def _prepare_claims(raw_claims: List[Dict[str, Any]], input_text: str, max_claims: int) -> tuple[List[Dict[str, Any]], bool]:
    claims: List[Dict[str, Any]] = []
    seen = set()
    for raw_claim in raw_claims[:max_claims]:
        text = _normalize_claim_text(raw_claim.get("text"))
        if not text or text in seen:
            continue
        seen.add(text)
        claims.append(
            {
                "text": text,
                "search_hint": (raw_claim.get("search_hint") or text).strip(),
            }
        )

    used_fallback = False
    if not claims:
        claims = _fallback_claims_from_input(input_text, max_claims)
        used_fallback = bool(claims)

    for i, claim in enumerate(claims, start=1):
        claim["id"] = f"claim-{i}"

    return claims, used_fallback


def node_extract_claims(state: AgentState) -> Dict[str, Any]:
    model = build_model(
        state["_model_name"],
        state.get("_llm_base_url"),
        state.get("_llm_api_key"),
    )
    max_claims = state["max_claims"]
    sys = extract_claims_system_prompt(max_claims)
    user = extract_claims_user_prompt(state["input_text"])
    out: ClaimsOutput = invoke_structured(model, ClaimsOutput, sys, user)

    raw_claims = [claim.model_dump() for claim in out.claims]
    claims, used_fallback = _prepare_claims(raw_claims, state["input_text"], max_claims)

    work: Dict[str, ClaimWork] = {}
    for claim in claims:
        cid = claim["id"]
        work[cid] = {
            "rounds": 0,
            "pro_sources": [],
            "con_sources": [],
            "judgement": None,
        }

    logs = [f"[extract_claims] extracted {len(claims)} claims"]
    if used_fallback:
        logs.append("[extract_claims] fallback to input-derived claim")

    first_id = claims[0]["id"] if claims else None
    return {
        "claims": claims,
        "work": work,
        "claim_index": 0,
        "active_claim_id": first_id,
        "logs": logs,
    }


def node_supervisor(state: AgentState) -> Dict[str, Any]:
    model = build_model(
        state["_model_name"],
        state.get("_llm_base_url"),
        state.get("_llm_api_key"),
    )
    claims = state.get("claims", [])
    idx = state.get("claim_index", 0)

    if not claims or idx >= len(claims):
        plan = SupervisorPlan(
            next_step="finish",
            rationale="no more claims to process",
        ).model_dump()
        return {"supervisor_plan": plan, "logs": ["[supervisor] finish (no more claims)"]}

    active = claims[idx]
    cid = active["id"]
    claim_work = state["work"][cid]

    if claim_work["rounds"] >= state["max_rounds_per_claim"]:
        new_idx = idx + 1
        nxt_id = claims[new_idx]["id"] if new_idx < len(claims) else None
        plan = SupervisorPlan(
            next_step="next_claim",
            rationale="reached max rounds for claim",
        ).model_dump()
        return {
            "claim_index": new_idx,
            "active_claim_id": nxt_id,
            "supervisor_plan": plan,
            "logs": [f"[supervisor] next_claim (max rounds) claim={cid}"],
        }

    if state["search_budget_remaining"] <= 0:
        plan = SupervisorPlan(next_step="finish", rationale="search budget exhausted").model_dump()
        return {"supervisor_plan": plan, "logs": ["[supervisor] finish (budget exhausted)"]}

    sys = supervisor_system_prompt()
    user = supervisor_user_prompt(
        active,
        claim_work,
        search_remaining=state["search_budget_remaining"],
        fetch_remaining=state["fetch_budget_remaining"],
        enable_fetch=state["enable_fetch"],
    )

    plan: SupervisorPlan = invoke_structured(model, SupervisorPlan, sys, user)
    plan_dict = plan.model_dump()

    if claim_work.get("judgement") is None and len(claim_work.get("con_sources", [])) == 0:
        plan_dict["run_con"] = True
    if claim_work.get("judgement") is None and len(claim_work.get("pro_sources", [])) == 0:
        plan_dict["run_pro"] = True

    if (not state["enable_fetch"]) or state["fetch_budget_remaining"] <= 0:
        plan_dict["use_fetch"] = False

    has_more_claims = idx < (len(claims) - 1)
    if plan_dict.get("next_step") == "finish" and has_more_claims and state["search_budget_remaining"] > 0:
        new_idx = idx + 1
        nxt_id = claims[new_idx]["id"] if new_idx < len(claims) else None
        plan_dict["next_step"] = "next_claim"
        plan_dict["rationale"] = (
            (plan_dict.get("rationale") or "") + " | override: still have remaining claims"
        )
        return {
            "claim_index": new_idx,
            "active_claim_id": nxt_id,
            "supervisor_plan": plan_dict,
            "logs": [f"[supervisor] next_claim (override finish) from claim={cid}"],
        }

    if plan_dict["next_step"] == "next_claim":
        new_idx = idx + 1
        nxt_id = claims[new_idx]["id"] if new_idx < len(claims) else None
        return {
            "claim_index": new_idx,
            "active_claim_id": nxt_id,
            "supervisor_plan": plan_dict,
            "logs": [f"[supervisor] next_claim (LLM) from claim={cid}"],
        }

    return {
        "active_claim_id": cid,
        "supervisor_plan": plan_dict,
        "logs": [f"[supervisor] {plan_dict['next_step']} claim={cid} | {plan_dict['rationale']}"],
    }


def node_pro_planner(state: AgentState) -> Dict[str, Any]:
    model = build_model(
        state["_model_name"],
        state.get("_llm_base_url"),
        state.get("_llm_api_key"),
    )
    active = state["claims"][state["claim_index"]]
    plan = state["supervisor_plan"] or {}

    sys = planner_system_prompt("pro")
    user = planner_user_prompt(active, plan, side="pro")
    out: SearchPlan = invoke_structured(model, SearchPlan, sys, user)
    plan_dict = out.model_dump()
    plan_dict["include_domains"] = _dedupe_list(
        plan_dict.get("include_domains", []) + (plan.get("prefer_domains") or [])
    )
    plan_dict["exclude_domains"] = _dedupe_list(
        plan_dict.get("exclude_domains", []) + (plan.get("avoid_domains") or [])
    )
    return {"pro_plan": plan_dict, "logs": [f"[pro_planner] {plan_dict['query']}"]}


def node_con_planner(state: AgentState) -> Dict[str, Any]:
    model = build_model(
        state["_model_name"],
        state.get("_llm_base_url"),
        state.get("_llm_api_key"),
    )
    active = state["claims"][state["claim_index"]]
    plan = state["supervisor_plan"] or {}

    sys = planner_system_prompt("con")
    user = planner_user_prompt(active, plan, side="con")
    out: SearchPlan = invoke_structured(model, SearchPlan, sys, user)
    plan_dict = out.model_dump()
    plan_dict["include_domains"] = _dedupe_list(
        plan_dict.get("include_domains", []) + (plan.get("prefer_domains") or [])
    )
    plan_dict["exclude_domains"] = _dedupe_list(
        plan_dict.get("exclude_domains", []) + (plan.get("avoid_domains") or [])
    )
    return {"con_plan": plan_dict, "logs": [f"[con_planner] {plan_dict['query']}"]}
