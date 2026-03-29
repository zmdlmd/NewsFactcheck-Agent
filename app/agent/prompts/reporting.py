from __future__ import annotations

import json
from typing import Any


def rewrite_summary_system_prompt() -> str:
    return (
        "你是事实核查报告的校对员，只做摘要改写。\n"
        "检查 summary 中出现的数字和单位是否与 sources 一致。\n"
        "只能使用 sources 中出现过的数字和单位，例如 billion、million、亿、万、%。\n"
        "如果无法确认数字是否一致，就删掉具体数值，改成更保守的表述。\n"
        "不得改变 verdict 的结论和含义，也不得添加新事实。\n"
        "只输出改写后的 summary 文本，不要输出其他内容。"
    )


def rewrite_summary_user_prompt(
    claim_text: str,
    verdict: str,
    summary: str,
    sources: list[dict[str, Any]],
) -> str:
    return (
        f"claim: {claim_text}\n"
        f"verdict: {verdict}\n"
        f"current summary: {summary}\n"
        f"sources: {json.dumps(sources[:5], ensure_ascii=False)}\n"
    )


def final_report_system_prompt() -> str:
    return (
        "你是报告撰写员。\n"
        "把每条主张的 judgement 和 sources 整理成 FinalReport。\n"
        "硬规则：\n"
        "1) sources 必须来自输入列表，即 pro_sources、con_sources 或 judgement.best_sources，不得新增。\n"
        "2) 如果 judgement.best_sources 为空，可以从 pro_sources 和 con_sources 中挑选 1 到 3 条作为 sources。\n"
        "3) summary 中出现的数字和单位必须与 sources 原文一致；如果不确定，就不要写具体数值。\n"
        "4) inconclusive 也必须给出来源，哪怕只是说明来源未包含所需统计。\n"
        "5) 输出必须是严格合法的 JSON，不要输出多余解释文字。"
    )


def final_report_user_prompt(pack: list[dict[str, Any]]) -> str:
    return (
        "写报告数据，注意 sources_for_report 是优先引用的来源列表：\n"
        f"{json.dumps(pack, ensure_ascii=False)}"
    )
