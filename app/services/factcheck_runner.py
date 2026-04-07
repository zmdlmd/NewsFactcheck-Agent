from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.tracers.langchain import wait_for_all_tracers

from app.agent.graph import build_graph
from app.agent.state_factory import build_initial_state
from app.core.config import Settings
from app.storage.sessions import RunRecord, make_run_id, make_session_id, save_run, utc_now_iso


@dataclass
class FactcheckRunResult:
    session_id: str
    run_id: str
    status: str
    final_report: dict[str, Any]
    final_markdown: str
    logs: list[str]
    retrieval_diagnostics: list[dict[str, Any]]
    saved_path: str
    error: dict[str, Any] | None = None


def _build_request_payload(
    *,
    input_text: str,
    session_id: str,
    search_budget: int | None,
    max_rounds_per_claim: int | None,
    enable_fetch: bool | None,
    fetch_budget: int | None,
    max_claims: int | None,
    request_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if request_payload is not None:
        return request_payload
    return {
        "input_text": input_text,
        "session_id": session_id,
        "search_budget": search_budget,
        "max_rounds_per_claim": max_rounds_per_claim,
        "enable_fetch": enable_fetch,
        "fetch_budget": fetch_budget,
        "max_claims": max_claims,
    }


def run_factcheck(
    *,
    input_text: str,
    settings: Settings,
    session_id: str | None = None,
    run_id: str | None = None,
    created_at: str | None = None,
    search_budget: int | None = None,
    max_rounds_per_claim: int | None = None,
    enable_fetch: bool | None = None,
    fetch_budget: int | None = None,
    max_claims: int | None = None,
    request_payload: dict[str, Any] | None = None,
    persist: bool = True,
    tags: list[str] | None = None,
) -> FactcheckRunResult:
    session_id = session_id or make_session_id()
    run_id = run_id or make_run_id()
    created_at = created_at or utc_now_iso()
    started_at = utc_now_iso()
    graph = build_graph()
    state = build_initial_state(
        input_text,
        settings,
        search_budget=search_budget,
        max_rounds_per_claim=max_rounds_per_claim,
        enable_fetch=enable_fetch,
        fetch_budget=fetch_budget,
        max_claims=max_claims,
    )
    payload = _build_request_payload(
        input_text=input_text,
        session_id=session_id,
        search_budget=search_budget,
        max_rounds_per_claim=max_rounds_per_claim,
        enable_fetch=enable_fetch,
        fetch_budget=fetch_budget,
        max_claims=max_claims,
        request_payload=request_payload,
    )

    saved_path = ""
    if persist:
        saved_path = save_run(
            settings,
            RunRecord(
                session_id=session_id,
                run_id=run_id,
                status="running",
                request=payload,
                response={},
                logs=[],
                error=None,
                created_at=created_at,
                updated_at=started_at,
                started_at=started_at,
                finished_at=None,
            ),
        )

    try:
        out = graph.invoke(
            state,
            config={
                "recursion_limit": 150,
                "configurable": {"thread_id": session_id},
                "metadata": {"session_id": session_id, "run_id": run_id},
                "tags": tags or ["factcheck-ma"],
            },
        )
        final_report = out.get("final_report") or {}
        final_markdown = out.get("final_markdown") or ""
        logs = out.get("logs") or []
        retrieval_diagnostics = out.get("retrieval_diagnostics") or []
        finished_at = utc_now_iso()

        if persist:
            saved_path = save_run(
                settings,
                RunRecord(
                    session_id=session_id,
                    run_id=run_id,
                    status="completed",
                    request=payload,
                    response={
                        "final_report": final_report,
                        "final_markdown": final_markdown,
                        "retrieval_diagnostics": retrieval_diagnostics,
                    },
                    logs=logs,
                    error=None,
                    created_at=created_at,
                    updated_at=finished_at,
                    started_at=started_at,
                    finished_at=finished_at,
                ),
            )

        return FactcheckRunResult(
            session_id=session_id,
            run_id=run_id,
            status="completed",
            final_report=final_report,
            final_markdown=final_markdown,
            logs=logs,
            retrieval_diagnostics=retrieval_diagnostics,
            saved_path=saved_path,
            error=None,
        )
    except Exception as exc:
        finished_at = utc_now_iso()
        logs = state.get("logs", [])
        retrieval_diagnostics = state.get("retrieval_diagnostics", [])
        error = {"type": exc.__class__.__name__, "message": str(exc)}
        if persist:
            saved_path = save_run(
                settings,
                RunRecord(
                    session_id=session_id,
                    run_id=run_id,
                    status="failed",
                    request=payload,
                    response={"retrieval_diagnostics": retrieval_diagnostics},
                    logs=logs,
                    error=error,
                    created_at=created_at,
                    updated_at=finished_at,
                    started_at=started_at,
                    finished_at=finished_at,
                ),
            )
        raise
    finally:
        try:
            wait_for_all_tracers()
        except Exception:
            pass
