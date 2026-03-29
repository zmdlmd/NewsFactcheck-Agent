import unittest
from unittest.mock import patch

from app.agent.models import ClaimsOutput
from app.agent.node_handlers.planning import node_extract_claims


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


if __name__ == "__main__":
    unittest.main()
