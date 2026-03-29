from typing import Any, Dict, List

def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 事实核查证据报告\n")

    lines.append("## 总结")
    lines.append(report.get("overall_summary", "").strip() or "（无）")
    lines.append("")

    lines.append("## 主张逐条结论")
    for item in report.get("claims", []) or []:
        claim_id = item.get("claim_id", "")
        claim = item.get("claim", "")
        verdict = item.get("verdict", "")
        conf = float(item.get("confidence", 0.0))
        summary = item.get("summary", "")

        lines.append(f"### {claim_id}：{claim}")
        lines.append(f"- 结论：**{verdict}**（置信度 {conf:.2f}）")
        lines.append(f"- 摘要：{summary}")

        sources = item.get("sources", []) or []
        if sources:
            lines.append("- 关键来源：")
            for s in sources[:5]:
                title = (s.get("title") or "").strip()
                url = (s.get("url") or "").strip()
                lines.append(f"  - {title} — {url}" if title else f"  - {url}")
        else:
            lines.append("- 关键来源：（无）")
        lines.append("")
    return "\n".join(lines)
