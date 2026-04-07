from __future__ import annotations

import json
from typing import Any, Literal


def extract_claims_system_prompt(max_claims: int) -> str:
    return (
        "You are a fact-checking claim extractor.\n"
        "Break the input into atomic, checkable factual claims.\n"
        "Avoid subjective opinions or merged multi-part claims.\n"
        f"Return between 1 and {max_claims} claims, keeping only the most important ones."
    )


def extract_claims_user_prompt(input_text: str) -> str:
    return f"Input text:\n{input_text}\n\nReturn claims."


def supervisor_system_prompt() -> str:
    return (
        "You are the fact-checking supervisor responsible for budget-aware control.\n"
        "Decide whether the next step is search, next_claim, or finish.\n"
        "Also decide whether to run pro/con search and whether fetch should be used.\n"
        "Only enable use_fetch when fetch is enabled and fetch budget remains.\n"
        "If the current claim is already clear and well-supported, you may move to next_claim.\n"
        "Avoid repetitive or low-yield searches.\n"
        "Do not choose finish unless there are no more claims or search budget is exhausted."
    )


def supervisor_user_prompt(
    active_claim: dict[str, Any],
    claim_work: dict[str, Any],
    *,
    search_remaining: int,
    fetch_remaining: int,
    enable_fetch: bool,
) -> str:
    judgement = json.dumps(claim_work.get("judgement"), ensure_ascii=False) if claim_work.get("judgement") else "None"
    return (
        f"Current claim: {active_claim['text']}\n"
        f"search_hint: {active_claim.get('search_hint')}\n"
        f"rounds={claim_work['rounds']} | "
        f"pro_sources={len(claim_work['pro_sources'])} "
        f"con_sources={len(claim_work['con_sources'])}\n"
        f"Current judgement: {judgement}\n"
        f"Budgets: search_remaining={search_remaining}, "
        f"fetch_remaining={fetch_remaining}, enable_fetch={enable_fetch}\n"
        "Return SupervisorPlan."
    )


def planner_system_prompt(side: Literal["pro", "con"]) -> str:
    role = "support-side researcher" if side == "pro" else "counter-side researcher"
    return (
        f"You are the {role}. Generate exactly one SearchPlan.\n"
        "Hard rules:\n"
        "1) Return JSON only.\n"
        "2) query must be a single-line string under 200 characters.\n"
        "3) include_domains and exclude_domains may contain at most 5 domain names each.\n"
        "4) Domains must be plain hostnames like example.com, not URLs and not site: operators.\n"
        "5) rag_filters must be a small key-value object for narrowing internal corpus retrieval.\n"
        "6) Each rag_filters value may be a string or a short list of strings.\n"
        "7) Good rag_filters use stable canonical keys such as lang, category, topic, institution, region, source_policy, or source_name.\n"
        "8) Preferred category values are report, data, announcement, news, research, policy, or reference.\n"
        "9) Preferred source_policy values are official, institutional, academic, media, reference, community, or internal.\n"
        "10) Use rag_filters only when you have a clear reason; otherwise return an empty object {}."
    )


def planner_user_prompt(
    active_claim: dict[str, Any],
    plan: dict[str, Any],
    *,
    side: Literal["pro", "con"],
    retrieval_mode: str,
    claim_profile: str,
) -> str:
    objective_key = "pro_objective" if side == "pro" else "con_objective"
    return (
        f"Claim: {active_claim['text']}\n"
        f"Hint: {active_claim.get('search_hint')}\n"
        f"Objective: {plan.get(objective_key)}\n"
        f"Retrieval mode: {retrieval_mode}\n"
        f"Claim profile: {claim_profile}\n"
        f"prefer_domains: {plan.get('prefer_domains')}\n"
        f"avoid_domains: {plan.get('avoid_domains')}\n"
        "If the claim profile suggests a stable internal slice of the corpus, use rag_filters.\n"
        "Numeric claims often align with report/data/statistics style evidence.\n"
        "Temporal claims often align with news/press/update/announcement style evidence.\n"
        "If language is clearly zh or en and your corpus tracks language metadata, lang can be a useful rag_filters key.\n"
        "If more than one stable corpus slice is clearly relevant, rag_filters values may be short lists.\n"
        "If you use category or source_policy filters, prefer the canonical values listed in the system instructions.\n"
        "If no clear internal metadata filter is justified, keep rag_filters as {}.\n"
        "Return SearchPlan."
    )
