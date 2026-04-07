import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.agent.graph import build_graph
from app.api import CheckAcceptedResponse, CheckRequest, CheckResponse, RunStatusResponse
from app.core.config import get_settings
from app.services.factcheck_runner import run_factcheck
from app.services.factcheck_tasks import submit_factcheck_task
from app.storage.sessions import load_latest_run, load_run_by_id

router = APIRouter()
log = logging.getLogger("routes")
_UI_PATH = Path(__file__).resolve().parent / "webui" / "index.html"


def _to_run_status_response(record: dict[str, Any]) -> RunStatusResponse:
    response = record.get("response") or {}
    return RunStatusResponse(
        session_id=record["session_id"],
        run_id=record["run_id"],
        status=record["status"],
        saved_path=record.get("saved_path", ""),
        final_report=response.get("final_report") or {},
        final_markdown=response.get("final_markdown") or "",
        logs=record.get("logs") or [],
        retrieval_diagnostics=response.get("retrieval_diagnostics") or [],
        error=record.get("error"),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
    )


@router.get("/graph/mermaid")
def graph_mermaid():
    graph = build_graph()
    g = graph.get_graph()
    if hasattr(g, "draw_mermaid"):
        return {"mermaid": g.draw_mermaid()}
    return {"mermaid": None, "error": "draw_mermaid() not available in this langgraph version"}


@router.get("/")
def root():
    s = get_settings()
    return {
        "name": "FactCheck Multi-Agent",
        "endpoints": {
            "docs": "/docs",
            "check_async": "POST /check",
            "check_sync": "POST /check/sync",
            "run_status": "GET /runs/{run_id}",
            "session_latest": "GET /sessions/{session_id}/latest",
        },
        "llm": {"model": s.model_name, "base_url": s.llm_base_url},
    }


@router.get("/ui", response_class=HTMLResponse)
def web_ui() -> HTMLResponse:
    return HTMLResponse(_UI_PATH.read_text(encoding="utf-8"))


@router.post("/check", response_model=CheckAcceptedResponse)
def check(req: CheckRequest) -> CheckAcceptedResponse:
    settings = get_settings()
    log.info("Queueing factcheck run using model=%s base_url=%s", settings.model_name, settings.llm_base_url)
    submitted = submit_factcheck_task(req, settings)
    return CheckAcceptedResponse(
        session_id=submitted.session_id,
        run_id=submitted.run_id,
        status=submitted.status,
        saved_path=submitted.saved_path,
        status_url=f"/runs/{submitted.run_id}",
    )


@router.post("/check/sync", response_model=CheckResponse)
def check_sync(req: CheckRequest) -> CheckResponse:
    settings = get_settings()
    log.info("Running synchronous factcheck using model=%s base_url=%s", settings.model_name, settings.llm_base_url)

    try:
        result = run_factcheck(
            input_text=req.input_text,
            settings=settings,
            session_id=req.session_id,
            search_budget=req.search_budget,
            max_rounds_per_claim=req.max_rounds_per_claim,
            enable_fetch=req.enable_fetch,
            fetch_budget=req.fetch_budget,
            max_claims=req.max_claims,
            request_payload=req.model_dump(),
            persist=True,
            tags=["factcheck-ma", "api", "sync"],
        )
    except Exception as exc:
        log.exception("synchronous factcheck run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CheckResponse(
        session_id=result.session_id,
        run_id=result.run_id,
        status=result.status,
        final_report=result.final_report,
        final_markdown=result.final_markdown,
        logs=result.logs,
        retrieval_diagnostics=result.retrieval_diagnostics,
        saved_path=result.saved_path,
        error=result.error,
    )


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: str) -> RunStatusResponse:
    settings = get_settings()
    record = load_run_by_id(settings, run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return _to_run_status_response(record)


@router.get("/sessions/{session_id}/latest", response_model=RunStatusResponse)
def get_latest_session_run(session_id: str) -> RunStatusResponse:
    settings = get_settings()
    record = load_latest_run(settings, session_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return _to_run_status_response(record)
