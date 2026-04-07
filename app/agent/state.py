import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

class ClaimWork(TypedDict):
    rounds: int
    pro_sources: List[Dict[str, Any]]
    con_sources: List[Dict[str, Any]]
    judgement: Optional[Dict[str, Any]]

class AgentState(TypedDict):
    input_text: str

    claims: List[Dict[str, Any]]
    claim_index: int
    active_claim_id: Optional[str]
    work: Dict[str, ClaimWork]

    search_budget_remaining: int
    fetch_budget_remaining: int

    max_rounds_per_claim: int
    enable_fetch: bool
    max_claims: int

    supervisor_plan: Optional[Dict[str, Any]]
    pro_plan: Optional[Dict[str, Any]]
    con_plan: Optional[Dict[str, Any]]

    logs: Annotated[List[str], operator.add]
    retrieval_diagnostics: Annotated[List[Dict[str, Any]], operator.add]

    final_report: Optional[Dict[str, Any]]
    final_markdown: Optional[str]

    _model_name: str
    _llm_api_key: Optional[str]
    _llm_base_url: Optional[str]
    _retrieval_mode: str
