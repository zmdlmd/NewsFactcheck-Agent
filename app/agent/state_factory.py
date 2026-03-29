from __future__ import annotations

from app.agent.state import AgentState
from app.core.config import Settings


def build_initial_state(
    input_text: str,
    settings: Settings,
    *,
    search_budget: int | None = None,
    max_rounds_per_claim: int | None = None,
    enable_fetch: bool | None = None,
    fetch_budget: int | None = None,
    max_claims: int | None = None,
) -> AgentState:
    state: AgentState = {
        "input_text": input_text,
        "claims": [],
        "claim_index": 0,
        "active_claim_id": None,
        "work": {},
        "search_budget_remaining": search_budget if search_budget is not None else settings.search_budget,
        "fetch_budget_remaining": fetch_budget if fetch_budget is not None else settings.fetch_budget,
        "max_rounds_per_claim": (
            max_rounds_per_claim
            if max_rounds_per_claim is not None
            else settings.max_rounds_per_claim
        ),
        "enable_fetch": enable_fetch if enable_fetch is not None else settings.enable_fetch,
        "max_claims": max_claims if max_claims is not None else settings.max_claims,
        "supervisor_plan": None,
        "pro_plan": None,
        "con_plan": None,
        "logs": [],
        "final_report": None,
        "final_markdown": None,
        "_model_name": settings.model_name,
        "_llm_api_key": settings.llm_api_key,
        "_llm_base_url": settings.llm_base_url,
    }
    return state
