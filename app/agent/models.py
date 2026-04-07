from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class ClaimItem(BaseModel):
    id: str = Field(description="主张ID")
    text: str = Field(description="可核查事实主张")
    search_hint: Optional[str] = Field(default=None, description="检索提示关键词")

class ClaimsOutput(BaseModel):
    claims: List[ClaimItem]

class SupervisorPlan(BaseModel):
    next_step: Literal["search", "next_claim", "finish"]
    rationale: str

    pro_objective: str = "寻找支持该主张的权威证据"
    con_objective: str = "寻找反驳/质疑该主张的权威证据"

    prefer_domains: List[str] = Field(default_factory=list)
    avoid_domains: List[str] = Field(default_factory=list)

    run_pro: bool = True
    run_con: bool = True

    use_fetch: bool = False

class SearchPlan(BaseModel):
    query: str
    include_domains: List[str] = Field(default_factory=list)
    exclude_domains: List[str] = Field(default_factory=list)
    rag_filters: Dict[str, str | List[str]] = Field(default_factory=dict)

class SourceItem(BaseModel):
    title: str
    url: str
    snippet: str
    source_type: Literal["web", "rag"] = "web"
    source_name: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    page_text: Optional[str] = None

class Judgement(BaseModel):
    verdict: Literal["supported", "refuted", "inconclusive"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    best_sources: List[SourceItem] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    suggested_followups: List[str] = Field(default_factory=list)

class ReportClaim(BaseModel):
    claim_id: str
    claim: str
    verdict: Literal["supported", "refuted", "inconclusive"]
    confidence: float
    summary: str
    sources: List[SourceItem] = Field(default_factory=list)

class FinalReport(BaseModel):
    overall_summary: str
    claims: List[ReportClaim]
