from typing import Literal, Optional

from pydantic import BaseModel, Field


RunStatus = Literal["queued", "running", "completed", "failed"]


class CheckRequest(BaseModel):
    input_text: str = Field(..., description="Text or claims to fact-check")
    session_id: Optional[str] = Field(default=None, description="Reuse an existing session when provided")
    search_budget: Optional[int] = None
    max_rounds_per_claim: Optional[int] = None
    enable_fetch: Optional[bool] = None
    fetch_budget: Optional[int] = None
    max_claims: Optional[int] = None


class RunError(BaseModel):
    type: str
    message: str


class CheckAcceptedResponse(BaseModel):
    session_id: str
    run_id: str
    status: RunStatus
    saved_path: str
    status_url: str


class CheckResponse(BaseModel):
    session_id: str
    run_id: str
    status: RunStatus = "completed"
    final_report: dict = Field(default_factory=dict)
    final_markdown: str = ""
    logs: list[str] = Field(default_factory=list)
    retrieval_diagnostics: list[dict] = Field(default_factory=list)
    saved_path: str = ""
    error: Optional[RunError] = None


class RunStatusResponse(BaseModel):
    session_id: str
    run_id: str
    status: RunStatus
    saved_path: str = ""
    final_report: dict = Field(default_factory=dict)
    final_markdown: str = ""
    logs: list[str] = Field(default_factory=list)
    retrieval_diagnostics: list[dict] = Field(default_factory=list)
    error: Optional[RunError] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
