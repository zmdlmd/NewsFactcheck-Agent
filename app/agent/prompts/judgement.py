from __future__ import annotations

import json
from typing import Any


def judgement_system_prompt() -> str:
    return (
        "你是证据裁判。\n"
        "基于给定证据判断主张属于 supported、refuted 或 inconclusive。\n"
        "只能使用输入证据内容，即 title、url、snippet、page_text，不要编造。\n"
        "best_sources 必须从输入来源中选择 1 到 3 条。"
    )


def judgement_user_prompt(
    claim_text: str,
    pro_sources: list[dict[str, Any]],
    con_sources: list[dict[str, Any]],
) -> str:
    return (
        f"主张：{claim_text}\n\n"
        f"pro_sources：{json.dumps(pro_sources[:8], ensure_ascii=False)}\n\n"
        f"con_sources：{json.dumps(con_sources[:8], ensure_ascii=False)}\n"
    )
