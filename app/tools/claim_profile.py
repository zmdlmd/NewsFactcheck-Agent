from __future__ import annotations

import re
from typing import Any

_NUMERIC_CLAIM_RE = re.compile(
    r"(?:\d[\d,.:/%-]*|"
    r"\b(?:percent|percentage|million|billion|trillion|revenue|sales|budget|gdp|population|rate|share|price)\b|"
    r"(?:美元|美金|亿元|万亿|万人|亿人|百分比|增长率|GDP|营收|票房|预算|人口|占比|比例))",
    re.IGNORECASE,
)

_TEMPORAL_CLAIM_RE = re.compile(
    r"(?:\b(?:today|current|currently|latest|recent|recently|new|newest|now|this year|this month|this week|"
    r"yesterday|tomorrow|announced|announcement|released|launch|won|elected|appointed|as of|quarter|q[1-4]|20\d{2})\b|"
    r"(?:今天|当前|目前|最新|最近|近日|今年|本月|本周|昨天|昨日|明天|刚刚|宣布|发布|任命|截至|现任|季度|近年))",
    re.IGNORECASE,
)


def detect_text_language(text: str) -> str:
    text = text or ""
    han_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z]{2,}", text))
    if han_chars >= 4 and latin_words >= 3:
        return "mixed"
    if han_chars >= 4:
        return "zh"
    if latin_words >= 3:
        return "en"
    return "unknown"


def build_claim_profile(claim_text: str) -> dict[str, Any]:
    years = sorted(set(re.findall(r"(?:19|20)\d{2}", claim_text or "")))
    return {
        "numeric": bool(_NUMERIC_CLAIM_RE.search(claim_text or "")),
        "temporal": bool(_TEMPORAL_CLAIM_RE.search(claim_text or "")),
        "years": years,
        "language": detect_text_language(claim_text or ""),
    }


def summarize_claim_profile(profile: dict[str, Any]) -> str:
    years = ",".join(profile.get("years") or []) or "none"
    language = profile.get("language") or "unknown"
    return (
        f"language={language}; "
        f"numeric={bool(profile.get('numeric'))}; "
        f"temporal={bool(profile.get('temporal'))}; "
        f"years={years}"
    )
