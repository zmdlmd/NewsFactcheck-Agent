import unittest
from unittest.mock import patch

from app.agent.models import ClaimsOutput, SearchPlan
from app.agent.node_handlers.planning import node_con_planner, node_extract_claims, node_pro_planner
from app.agent.prompts.planning import planner_user_prompt


class ExtractClaimsTests(unittest.TestCase):
    def test_falls_back_to_input_when_model_returns_empty_claims(self):
        state = {
            "input_text": "请核查：地球围绕太阳公转。",
            "max_claims": 1,
            "_model_name": "test-model",
            "_llm_api_key": "secret",
            "_llm_base_url": "https://example.com/v1",
        }

        with (
            patch("app.agent.node_handlers.planning.build_model", return_value=object()),
            patch(
                "app.agent.node_handlers.planning.invoke_structured",
                return_value=ClaimsOutput(claims=[]),
            ),
        ):
            result = node_extract_claims(state)

        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(result["claims"][0]["id"], "claim-1")
        self.assertEqual(result["claims"][0]["text"], "地球围绕太阳公转。")
        self.assertEqual(result["claims"][0]["search_hint"], "地球围绕太阳公转。")
        self.assertEqual(result["active_claim_id"], "claim-1")
        self.assertIn("[extract_claims] fallback to input-derived claim", result["logs"])


class PlannerTests(unittest.TestCase):
    def test_planner_user_prompt_includes_claim_profile_and_retrieval_mode(self):
        prompt = planner_user_prompt(
            {"id": "claim-1", "text": "Revenue reached $5 billion in 2025.", "search_hint": "revenue 2025"},
            {
                "pro_objective": "Find supporting evidence",
                "prefer_domains": ["example.com"],
                "avoid_domains": [],
            },
            side="pro",
            retrieval_mode="hybrid",
            claim_profile="language=en; numeric=True; temporal=True; years=2025",
        )

        self.assertIn("Retrieval mode: hybrid", prompt)
        self.assertIn("Claim profile: language=en; numeric=True; temporal=True; years=2025", prompt)

    def test_pro_planner_normalizes_rag_filters(self):
        state = {
            "claims": [{"id": "claim-1", "text": "A space claim", "search_hint": "space claim"}],
            "claim_index": 0,
            "_retrieval_mode": "hybrid",
            "supervisor_plan": {
                "pro_objective": "Find supporting evidence",
                "prefer_domains": ["nasa.gov"],
                "avoid_domains": ["reddit.com"],
            },
            "_model_name": "test-model",
            "_llm_api_key": "secret",
            "_llm_base_url": "https://example.com/v1",
        }

        with (
            patch("app.agent.node_handlers.planning.build_model", return_value=object()),
            patch(
                "app.agent.node_handlers.planning.invoke_structured",
                return_value=SearchPlan(
                    query="space claim",
                    include_domains=["nasa.gov"],
                    exclude_domains=["reddit.com"],
                    rag_filters={
                        "language": "English",
                        "type": "press release",
                        "policy": "gov",
                        "topic": "Space Exploration",
                        "empty": "",
                    },
                ),
            ),
        ):
            result = node_pro_planner(state)

        self.assertEqual(result["pro_plan"]["query"], "space claim")
        self.assertEqual(result["pro_plan"]["include_domains"], ["nasa.gov"])
        self.assertEqual(result["pro_plan"]["exclude_domains"], ["reddit.com"])
        self.assertEqual(
            result["pro_plan"]["rag_filters"],
            {
                "lang": ["en"],
                "category": ["announcement"],
                "source_policy": ["official"],
                "topic": ["space-exploration"],
            },
        )

    def test_pro_planner_adds_stable_defaults_in_hybrid_mode(self):
        state = {
            "claims": [{"id": "claim-1", "text": "Revenue reached 5 billion dollars.", "search_hint": "revenue"}],
            "claim_index": 0,
            "_retrieval_mode": "hybrid",
            "supervisor_plan": {
                "pro_objective": "Find supporting evidence",
                "prefer_domains": [],
                "avoid_domains": [],
            },
            "_model_name": "test-model",
            "_llm_api_key": "secret",
            "_llm_base_url": "https://example.com/v1",
        }

        with (
            patch("app.agent.node_handlers.planning.build_model", return_value=object()),
            patch(
                "app.agent.node_handlers.planning.invoke_structured",
                return_value=SearchPlan(
                    query="revenue",
                    include_domains=[],
                    exclude_domains=[],
                    rag_filters={},
                ),
            ),
        ):
            result = node_pro_planner(state)

        self.assertEqual(result["pro_plan"]["rag_filters"], {"lang": ["en"], "category": ["report"]})

    def test_con_planner_defaults_empty_rag_filters(self):
        state = {
            "claims": [{"id": "claim-1", "text": "A company claim", "search_hint": "company claim"}],
            "claim_index": 0,
            "_retrieval_mode": "web",
            "supervisor_plan": {
                "con_objective": "Find contradictory evidence",
                "prefer_domains": [],
                "avoid_domains": [],
            },
            "_model_name": "test-model",
            "_llm_api_key": "secret",
            "_llm_base_url": "https://example.com/v1",
        }

        with (
            patch("app.agent.node_handlers.planning.build_model", return_value=object()),
            patch(
                "app.agent.node_handlers.planning.invoke_structured",
                return_value=SearchPlan(
                    query="company claim",
                    include_domains=[],
                    exclude_domains=[],
                    rag_filters={},
                ),
            ),
        ):
            result = node_con_planner(state)

        self.assertEqual(result["con_plan"]["rag_filters"], {})


if __name__ == "__main__":
    unittest.main()
