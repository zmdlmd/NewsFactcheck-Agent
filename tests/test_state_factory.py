import unittest

from app.agent.state_factory import build_initial_state
from app.core.config import Settings


class BuildInitialStateTests(unittest.TestCase):
    def test_uses_settings_defaults(self):
        settings = Settings(
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

        state = build_initial_state("hello world", settings)

        self.assertEqual(state["input_text"], "hello world")
        self.assertEqual(state["search_budget_remaining"], 10)
        self.assertEqual(state["fetch_budget_remaining"], 4)
        self.assertEqual(state["max_rounds_per_claim"], 2)
        self.assertFalse(state["enable_fetch"])
        self.assertEqual(state["max_claims"], 5)
        self.assertEqual(state["_model_name"], "test-model")
        self.assertEqual(state["_llm_api_key"], "secret")
        self.assertEqual(state["_llm_base_url"], "https://example.com/v1")
        self.assertEqual(state["claims"], [])
        self.assertEqual(state["work"], {})
        self.assertEqual(state["logs"], [])
        self.assertIsNone(state["final_report"])
        self.assertIsNone(state["final_markdown"])

    def test_applies_request_overrides(self):
        settings = Settings(
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

        state = build_initial_state(
            "hello world",
            settings,
            search_budget=3,
            max_rounds_per_claim=7,
            enable_fetch=True,
            fetch_budget=1,
            max_claims=2,
        )

        self.assertEqual(state["search_budget_remaining"], 3)
        self.assertEqual(state["fetch_budget_remaining"], 1)
        self.assertEqual(state["max_rounds_per_claim"], 7)
        self.assertTrue(state["enable_fetch"])
        self.assertEqual(state["max_claims"], 2)


if __name__ == "__main__":
    unittest.main()
