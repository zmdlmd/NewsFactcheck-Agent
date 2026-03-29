from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from app.api import CheckRequest
from app.core.config import Settings
from app.services.factcheck_runner import run_factcheck
from app.storage.sessions import (
    RunRecord,
    list_pending_runs,
    make_run_id,
    make_session_id,
    save_run,
    utc_now_iso,
)

log = logging.getLogger("factcheck_tasks")


@dataclass
class SubmittedRun:
    session_id: str
    run_id: str
    status: str
    saved_path: str


@dataclass
class QueuedRun:
    req: CheckRequest
    session_id: str
    run_id: str
    created_at: str


class FactcheckTaskWorker:
    def __init__(self) -> None:
        self._queue: queue.Queue[QueuedRun] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._settings: Settings | None = None
        self._lock = threading.Lock()
        self._queued_or_running: set[str] = set()

    def start(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="factcheck-task-worker",
                daemon=True,
            )
            self._thread.start()

        self.recover_pending_runs(settings)

    def submit(self, req: CheckRequest, settings: Settings) -> SubmittedRun:
        self.start(settings)
        session_id = req.session_id or make_session_id()
        run_id = make_run_id()
        created_at = utc_now_iso()
        saved_path = save_run(
            settings,
            RunRecord(
                session_id=session_id,
                run_id=run_id,
                status="queued",
                request={**req.model_dump(), "session_id": session_id},
                response={},
                logs=[],
                error=None,
                created_at=created_at,
                updated_at=created_at,
                started_at=None,
                finished_at=None,
            ),
        )
        self._enqueue(
            QueuedRun(
                req=req,
                session_id=session_id,
                run_id=run_id,
                created_at=created_at,
            )
        )
        return SubmittedRun(
            session_id=session_id,
            run_id=run_id,
            status="queued",
            saved_path=saved_path,
        )

    def recover_pending_runs(self, settings: Settings) -> int:
        pending = list_pending_runs(settings)
        recovered = 0
        for record in pending:
            request = dict(record.get("request") or {})
            input_text = request.get("input_text")
            if not input_text:
                continue
            req = CheckRequest(**request)
            queued = QueuedRun(
                req=req,
                session_id=record["session_id"],
                run_id=record["run_id"],
                created_at=record.get("created_at") or utc_now_iso(),
            )
            if self._enqueue(queued):
                recovered += 1
        if recovered:
            log.info("Recovered %s pending factcheck run(s)", recovered)
        return recovered

    def _enqueue(self, queued: QueuedRun) -> bool:
        with self._lock:
            if queued.run_id in self._queued_or_running:
                return False
            self._queued_or_running.add(queued.run_id)
        self._queue.put(queued)
        return True

    def _worker_loop(self) -> None:
        while True:
            queued = self._queue.get()
            try:
                self._run_one(queued)
            finally:
                with self._lock:
                    self._queued_or_running.discard(queued.run_id)
                self._queue.task_done()

    def _run_one(self, queued: QueuedRun) -> None:
        settings = self._settings
        if settings is None:
            log.error("Task worker started without settings")
            return

        try:
            run_factcheck(
                input_text=queued.req.input_text,
                settings=settings,
                session_id=queued.session_id,
                run_id=queued.run_id,
                created_at=queued.created_at,
                search_budget=queued.req.search_budget,
                max_rounds_per_claim=queued.req.max_rounds_per_claim,
                enable_fetch=queued.req.enable_fetch,
                fetch_budget=queued.req.fetch_budget,
                max_claims=queued.req.max_claims,
                request_payload={**queued.req.model_dump(), "session_id": queued.session_id},
                persist=True,
                tags=["factcheck-ma", "api", "async", "worker"],
            )
        except Exception:
            log.exception(
                "background factcheck run failed | session_id=%s run_id=%s",
                queued.session_id,
                queued.run_id,
            )


_TASK_WORKER = FactcheckTaskWorker()


def get_task_worker() -> FactcheckTaskWorker:
    return _TASK_WORKER


def start_factcheck_worker(settings: Settings) -> None:
    get_task_worker().start(settings)


def submit_factcheck_task(req: CheckRequest, settings: Settings) -> SubmittedRun:
    return get_task_worker().submit(req, settings)
