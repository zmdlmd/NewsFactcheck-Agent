from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.agent.node_handlers import (
    node_con_planner,
    node_con_search,
    node_extract_claims,
    node_fetch_key_pages,
    node_judge,
    node_pro_planner,
    node_pro_search,
    node_supervisor,
    node_write_report,
)
from app.agent.state import AgentState


def route_from_supervisor(state: AgentState) -> Literal[
    "pro_planner", "supervisor", "write_report"
]:
    step = (state.get("supervisor_plan") or {}).get("next_step")
    if step == "search":
        return "pro_planner"
    if step == "next_claim":
        return "supervisor"
    return "write_report"


def route_after_con_search(state: AgentState) -> Literal["fetch_key_pages", "judge"]:
    plan = state.get("supervisor_plan") or {}
    if state.get("enable_fetch") and plan.get("use_fetch") and state.get("fetch_budget_remaining", 0) > 0:
        return "fetch_key_pages"
    return "judge"


def build_graph():
    b = StateGraph(AgentState)

    b.add_node("extract_claims", node_extract_claims)
    b.add_node("supervisor", node_supervisor)

    b.add_node("pro_planner", node_pro_planner)
    b.add_node("con_planner", node_con_planner)

    b.add_node("pro_search", node_pro_search)
    b.add_node("con_search", node_con_search)

    b.add_node("fetch_key_pages", node_fetch_key_pages)
    b.add_node("judge", node_judge)

    b.add_node("write_report", node_write_report)

    b.add_edge(START, "extract_claims")
    b.add_edge("extract_claims", "supervisor")

    b.add_conditional_edges("supervisor", route_from_supervisor, ["pro_planner", "supervisor", "write_report"])

    b.add_edge("pro_planner", "con_planner")
    b.add_edge("con_planner", "pro_search")
    b.add_edge("pro_search", "con_search")
    b.add_conditional_edges("con_search", route_after_con_search, ["fetch_key_pages", "judge"])
    b.add_edge("fetch_key_pages", "judge")
    b.add_edge("judge", "supervisor")

    b.add_edge("write_report", END)
    return b.compile()
