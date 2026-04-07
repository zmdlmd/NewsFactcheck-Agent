import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.factcheck_runner import FactcheckRunResult
from app.services.factcheck_tasks import SubmittedRun


class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.worker_patcher = patch("app.main.start_factcheck_worker")
        self.worker_patcher.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.worker_patcher.stop()

    def test_async_check_returns_accepted_run(self):
        with patch(
            "app.routes.submit_factcheck_task",
            return_value=SubmittedRun(
                session_id="session-1",
                run_id="run-1",
                status="queued",
                saved_path="./data/sessions/session-1/run-1.json",
            ),
        ):
            resp = self.client.post("/check", json={"input_text": "claim"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(),
            {
                "session_id": "session-1",
                "run_id": "run-1",
                "status": "queued",
                "saved_path": "./data/sessions/session-1/run-1.json",
                "status_url": "/runs/run-1",
            },
        )

    def test_ui_route_returns_html(self):
        resp = self.client.get("/ui")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("NewsFactcheck Agent", resp.text)

    def test_sync_check_returns_completed_payload(self):
        with patch(
            "app.routes.run_factcheck",
            return_value=FactcheckRunResult(
                session_id="session-2",
                run_id="run-2",
                status="completed",
                final_report={"overall_summary": "ok", "claims": []},
                final_markdown="# ok",
                logs=["done"],
                retrieval_diagnostics=[{"side": "pro", "mode": "hybrid"}],
                saved_path="./data/sessions/session-2/run-2.json",
                error=None,
            ),
        ):
            resp = self.client.post("/check/sync", json={"input_text": "claim"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "completed")
        self.assertEqual(resp.json()["run_id"], "run-2")
        self.assertEqual(resp.json()["retrieval_diagnostics"], [{"side": "pro", "mode": "hybrid"}])

    def test_get_run_status_reads_persisted_record(self):
        record = {
            "session_id": "session-3",
            "run_id": "run-3",
            "status": "failed",
            "saved_path": "./data/sessions/session-3/run-3.json",
            "logs": ["starting"],
            "response": {"retrieval_diagnostics": [{"side": "con", "mode": "rag"}]},
            "error": {"type": "RuntimeError", "message": "boom"},
            "created_at": "created",
            "updated_at": "updated",
            "started_at": "started",
            "finished_at": "finished",
        }
        with patch("app.routes.load_run_by_id", return_value=record):
            resp = self.client.get("/runs/run-3")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["error"]["message"], "boom")
        self.assertEqual(body["saved_path"], "./data/sessions/session-3/run-3.json")
        self.assertEqual(body["retrieval_diagnostics"], [{"side": "con", "mode": "rag"}])

    def test_get_latest_session_run_reads_latest_record(self):
        record = {
            "session_id": "session-4",
            "run_id": "run-4",
            "status": "completed",
            "saved_path": "./data/sessions/session-4/run-4.json",
            "response": {
                "final_report": {"overall_summary": "ok", "claims": []},
                "final_markdown": "# ok",
                "retrieval_diagnostics": [{"side": "pro", "mode": "hybrid"}],
            },
            "logs": ["done"],
            "error": None,
            "created_at": "created",
            "updated_at": "updated",
            "started_at": "started",
            "finished_at": "finished",
        }
        with patch("app.routes.load_latest_run", return_value=record):
            resp = self.client.get("/sessions/session-4/latest")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["run_id"], "run-4")
        self.assertEqual(resp.json()["status"], "completed")
        self.assertEqual(resp.json()["retrieval_diagnostics"], [{"side": "pro", "mode": "hybrid"}])


if __name__ == "__main__":
    unittest.main()
