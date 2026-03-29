from __future__ import annotations

import json
from typing import Any, Literal


def extract_claims_system_prompt(max_claims: int) -> str:
    return (
        "你是事实核查系统的主张拆分员。\n"
        "把输入拆成可核查、原子化的事实主张，避免主观判断。\n"
        "每个 claim 只能包含一个事实。\n"
        "不要把多条事实合并到同一个 claim。\n"
        f"输出 1 到 {max_claims} 条，挑最关键的主张。"
    )


def extract_claims_user_prompt(input_text: str) -> str:
    return f"输入文本：\n{input_text}\n\n请输出 claims。"


def supervisor_system_prompt() -> str:
    return (
        "你是事实核查系统的 Supervisor，负责总控和预算调度。\n"
        "在有限预算下决定：search / next_claim / finish。\n"
        "并决定这一轮是否执行 pro/con 检索，以及是否 use_fetch。\n"
        "只有 enable_fetch 为真且仍有抓取预算时，才可以 use_fetch。\n"
        "如果当前结论已经清晰且证据足够，可以选择 next_claim。\n"
        "避免重复或收益很低的检索。\n"
        "除非没有更多主张，或者检索预算已经耗尽，否则不要选择 finish。"
    )


def supervisor_user_prompt(
    active_claim: dict[str, Any],
    claim_work: dict[str, Any],
    *,
    search_remaining: int,
    fetch_remaining: int,
    enable_fetch: bool,
) -> str:
    return (
        f"当前主张：{active_claim['text']}\n"
        f"search_hint：{active_claim.get('search_hint')}\n"
        f"rounds={claim_work['rounds']} | "
        f"pro_sources={len(claim_work['pro_sources'])} "
        f"con_sources={len(claim_work['con_sources'])}\n"
        f"当前结论：{json.dumps(claim_work.get('judgement'), ensure_ascii=False) if claim_work.get('judgement') else 'None'}\n"
        f"预算：search_remaining={search_remaining}, "
        f"fetch_remaining={fetch_remaining}, enable_fetch={enable_fetch}\n"
        "请输出 SupervisorPlan。"
    )


def planner_system_prompt(side: Literal["pro", "con"]) -> str:
    role = "支持方研究员" if side == "pro" else "反对方研究员"
    return (
        f"你是{role}，只负责生成一个网页检索 SearchPlan。\n"
        "硬规则：\n"
        "1) 只输出 JSON，不要输出 Markdown、解释或多余文本。\n"
        "2) query 必须是单行字符串，长度不超过 200 个字符。\n"
        "3) include_domains / exclude_domains 每个最多 5 个域名。\n"
        "4) 域名只写 example.com 这种格式，不要写 URL，也不要写 site:。"
    )


def planner_user_prompt(
    active_claim: dict[str, Any],
    plan: dict[str, Any],
    *,
    side: Literal["pro", "con"],
) -> str:
    objective_key = "pro_objective" if side == "pro" else "con_objective"
    return (
        f"主张：{active_claim['text']}\n"
        f"hint：{active_claim.get('search_hint')}\n"
        f"目标：{plan.get(objective_key)}\n"
        f"prefer_domains：{plan.get('prefer_domains')}\n"
        f"avoid_domains：{plan.get('avoid_domains')}\n"
        "输出 SearchPlan。"
    )
