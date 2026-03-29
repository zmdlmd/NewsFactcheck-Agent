import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.services.factcheck_runner import run_factcheck


class FakeGraph:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.last_state = None
        self.last_config = None

    def invoke(self, state, config=None):
        self.last_state = state
        self.last_config = config
        if self.error is not None:
            raise self.error
        return self.result


class RunFactcheckTests(unittest.TestCase):
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

    def test_run_factcheck_wires_graph_and_persists_lifecycle(self):
        graph = FakeGraph(
            result={
                "final_report": {"overall_summary": "ok", "claims": []},
                "final_markdown": "# ok",
                "logs": ["done"],
            }
        )

        with (
            patch("app.services.factcheck_runner.build_graph", return_value=graph),
            patch("app.services.factcheck_runner.make_session_id", return_value="session-1"),
            patch("app.services.factcheck_runner.make_run_id", return_value="run-1"),
            patch("app.services.factcheck_runner.utc_now_iso", side_effect=["created", "started", "finished"]),
            patch("app.services.factcheck_runner.save_run", side_effect=["queued/path.json", "saved/path.json"]) as save_run,
            patch("app.services.factcheck_runner.wait_for_all_tracers") as wait_for_all_tracers,
        ):
            result = run_factcheck(
                input_text="claim text",
                settings=self.settings,
                search_budget=3,
                max_rounds_per_claim=7,
                enable_fetch=True,
                fetch_budget=1,
                max_claims=2,
                request_payload={"input_text": "claim text"},
                persist=True,
                tags=["factcheck-ma", "test"],
            )

        self.assertEqual(graph.last_state["input_text"], "claim text")
        self.assertEqual(graph.last_state["search_budget_remaining"], 3)
        self.assertEqual(graph.last_state["fetch_budget_remaining"], 1)
        self.assertEqual(graph.last_state["max_rounds_per_claim"], 7)
        self.assertTrue(graph.last_state["enable_fetch"])
        self.assertEqual(graph.last_state["max_claims"], 2)
        self.assertEqual(
            graph.last_config,
            {
                "recursion_limit": 150,
                "configurable": {"thread_id": "session-1"},
                "metadata": {"session_id": "session-1", "run_id": "run-1"},
                "tags": ["factcheck-ma", "test"],
            },
        )
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.run_id, "run-1")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.saved_path, "saved/path.json")
        wait_for_all_tracers.assert_called_once()
        self.assertEqual(save_run.call_count, 2)

        first_record = save_run.call_args_list[0].args[1]
        second_record = save_run.call_args_list[1].args[1]
        self.assertEqual(first_record.status, "running")
        self.assertEqual(first_record.created_at, "created")
        self.assertEqual(first_record.updated_at, "started")
        self.assertEqual(first_record.started_at, "started")
        self.assertIsNone(first_record.finished_at)
        self.assertEqual(second_record.status, "completed")
        self.assertEqual(second_record.updated_at, "finished")
        self.assertEqual(second_record.finished_at, "finished")
        self.assertEqual(second_record.response["final_report"], {"overall_summary": "ok", "claims": []})
        self.assertEqual(second_record.logs, ["done"])

    def test_run_factcheck_persists_failure(self):
        graph = FakeGraph(error=RuntimeError("boom"))

        with (
            patch("app.services.factcheck_runner.build_graph", return_value=graph),
            patch("app.services.factcheck_runner.make_session_id", return_value="session-3"),
            patch("app.services.factcheck_runner.make_run_id", return_value="run-3"),
            patch("app.services.factcheck_runner.utc_now_iso", side_effect=["created", "started", "finished"]),
            patch("app.services.factcheck_runner.save_run", side_effect=["running/path.json", "failed/path.json"]) as save_run,
            patch("app.services.factcheck_runner.wait_for_all_tracers") as wait_for_all_tracers,
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                run_factcheck(
                    input_text="claim text",
                    settings=self.settings,
                    persist=True,
                )

        wait_for_all_tracers.assert_called_once()
        self.assertEqual(save_run.call_count, 2)
        first_record = save_run.call_args_list[0].args[1]
        second_record = save_run.call_args_list[1].args[1]
        self.assertEqual(first_record.status, "running")
        self.assertEqual(second_record.status, "failed")
        self.assertEqual(second_record.error, {"type": "RuntimeError", "message": "boom"})
        self.assertEqual(second_record.finished_at, "finished")

    def test_run_factcheck_can_skip_persistence(self):
        graph = FakeGraph(
            result={
                "final_report": {"overall_summary": "ok", "claims": []},
                "final_markdown": "# ok",
                "logs": [],
            }
        )

        with (
            patch("app.services.factcheck_runner.build_graph", return_value=graph),
            patch("app.services.factcheck_runner.make_session_id", return_value="session-2"),
            patch("app.services.factcheck_runner.make_run_id", return_value="run-2"),
            patch("app.services.factcheck_runner.utc_now_iso", side_effect=["created", "started", "finished"]),
            patch("app.services.factcheck_runner.save_run") as save_run,
            patch("app.services.factcheck_runner.wait_for_all_tracers"),
        ):
            result = run_factcheck(
                input_text="claim text",
                settings=self.settings,
                persist=False,
            )

        self.assertEqual(result.session_id, "session-2")
        self.assertEqual(result.run_id, "run-2")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.saved_path, "")
        save_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
