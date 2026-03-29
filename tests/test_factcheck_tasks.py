import unittest
from unittest.mock import MagicMock, patch

from app.api import CheckRequest
from app.core.config import Settings
from app.services.factcheck_tasks import FactcheckTaskWorker


class FactcheckTaskWorkerTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            model_name="test-model",
            max_claims=5,
            llm_api_key="secret",
            llm_base_url="https://example.com/v1",
            search_budget=10,
            max_rounds_per_claim=2,
            enable_fetch=False,
            fetch_budget=4,
            data_dir="./data",
        )

    def test_submit_persists_queued_run_and_enqueues(self):
        worker = FactcheckTaskWorker()
        req = CheckRequest(input_text="claim")

        with (
            patch.object(worker, "start") as start,
            patch.object(worker, "_enqueue", return_value=True) as enqueue,
            patch("app.services.factcheck_tasks.make_session_id", return_value="session-1"),
            patch("app.services.factcheck_tasks.make_run_id", return_value="run-1"),
            patch("app.services.factcheck_tasks.utc_now_iso", return_value="created"),
            patch("app.services.factcheck_tasks.save_run", return_value="./data/sessions/session-1/run-1.json") as save_run,
        ):
            submitted = worker.submit(req, self.settings)

        start.assert_called_once_with(self.settings)
        enqueue.assert_called_once()
        queued = enqueue.call_args.args[0]
        self.assertEqual(queued.session_id, "session-1")
        self.assertEqual(queued.run_id, "run-1")
        self.assertEqual(queued.created_at, "created")
        self.assertEqual(submitted.session_id, "session-1")
        self.assertEqual(submitted.run_id, "run-1")
        self.assertEqual(submitted.status, "queued")
        self.assertEqual(submitted.saved_path, "./data/sessions/session-1/run-1.json")

        run_record = save_run.call_args.args[1]
        self.assertEqual(run_record.status, "queued")
        self.assertEqual(run_record.request["session_id"], "session-1")

    def test_recover_pending_runs_requeues_unfinished_records(self):
        worker = FactcheckTaskWorker()
        worker._enqueue = MagicMock(return_value=True)
        records = [
            {
                "session_id": "session-1",
                "run_id": "run-1",
                "status": "queued",
                "request": {"input_text": "claim 1", "session_id": "session-1"},
                "created_at": "created-1",
            },
            {
                "session_id": "session-2",
                "run_id": "run-2",
                "status": "running",
                "request": {"input_text": "claim 2", "session_id": "session-2", "search_budget": 3},
                "created_at": "created-2",
            },
        ]

        with patch("app.services.factcheck_tasks.list_pending_runs", return_value=records):
            recovered = worker.recover_pending_runs(self.settings)

        self.assertEqual(recovered, 2)
        self.assertEqual(worker._enqueue.call_count, 2)
        first = worker._enqueue.call_args_list[0].args[0]
        second = worker._enqueue.call_args_list[1].args[0]
        self.assertEqual(first.req.input_text, "claim 1")
        self.assertEqual(first.run_id, "run-1")
        self.assertEqual(second.req.search_budget, 3)
        self.assertEqual(second.run_id, "run-2")

    def test_start_initializes_thread_once_and_recovers(self):
        worker = FactcheckTaskWorker()
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = False

        with (
            patch("app.services.factcheck_tasks.threading.Thread", return_value=fake_thread) as thread_cls,
            patch.object(worker, "recover_pending_runs", return_value=2) as recover_pending_runs,
        ):
            worker.start(self.settings)

        thread_cls.assert_called_once()
        fake_thread.start.assert_called_once()
        recover_pending_runs.assert_called_once_with(self.settings)
        self.assertIs(worker._settings, self.settings)


if __name__ == "__main__":
    unittest.main()
