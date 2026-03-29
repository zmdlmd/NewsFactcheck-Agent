import unittest
from unittest.mock import patch

from app.agent.node_handlers.research import node_fetch_key_pages


class ResearchNodeTests(unittest.TestCase):
    def test_node_fetch_key_pages_prefers_report_like_source_for_numeric_claim(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 1,
            "claim_index": 0,
            "claims": [{"id": "claim-1", "text": "The company reported revenue of $5 billion in 2025."}],
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [
                        {
                            "url": "https://example.com/feature-story",
                            "title": "Feature Story",
                            "snippet": "A broad feature article with background context and several paragraphs of narrative text.",
                        },
                        {
                            "url": "https://example.com/annual-report-2025.pdf",
                            "title": "Annual Report 2025",
                            "snippet": "Official revenue report with consolidated statements and detailed financial data.",
                        },
                    ],
                    "con_sources": [],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", return_value="report text") as fetch_page:
            result = node_fetch_key_pages(state)

        self.assertEqual(result["logs"], ["[fetch] attempted=1 accepted=1 remaining_fetch=0"])
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][1]["page_text"], "report text")
        fetch_page.assert_called_once_with("https://example.com/annual-report-2025.pdf")

    def test_node_fetch_key_pages_prefers_news_like_source_for_temporal_claim(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 1,
            "claim_index": 0,
            "claims": [{"id": "claim-1", "text": "The company announced a new CEO in 2026."}],
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [
                        {
                            "url": "https://example.com/investor/annual-report-2025.pdf",
                            "title": "Annual Report 2025",
                            "snippet": "Long investor report with background information, governance notes, and historical company details.",
                        },
                        {
                            "url": "https://example.com/news/2026-ceo-announcement",
                            "title": "CEO Announcement",
                            "snippet": "Official news update about the newly announced chief executive.",
                        },
                    ],
                    "con_sources": [],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", return_value="news text") as fetch_page:
            result = node_fetch_key_pages(state)

        self.assertEqual(result["logs"], ["[fetch] attempted=1 accepted=1 remaining_fetch=0"])
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][1]["page_text"], "news text")
        fetch_page.assert_called_once_with("https://example.com/news/2026-ceo-announcement")

    def test_node_fetch_key_pages_prefers_higher_priority_source_within_side(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 1,
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [
                        {"url": "https://example.com/blog", "title": "Blog", "snippet": "Short blog note."},
                        {
                            "url": "https://www.nasa.gov/earth-orbit",
                            "title": "NASA Earth Orbit",
                            "snippet": "Official NASA explanation of Earth's orbit around the Sun with detailed scientific context.",
                        },
                    ],
                    "con_sources": [],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", return_value="nasa text") as fetch_page:
            result = node_fetch_key_pages(state)

        self.assertEqual(result["logs"], ["[fetch] attempted=1 accepted=1 remaining_fetch=0"])
        self.assertIsNone(state["work"]["claim-1"]["pro_sources"][0].get("page_text"))
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][1]["page_text"], "nasa text")
        fetch_page.assert_called_once_with("https://www.nasa.gov/earth-orbit")

    def test_node_fetch_key_pages_updates_sources_and_budget(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 2,
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [{"url": "https://example.com/pro", "title": "Pro", "snippet": "p"}],
                    "con_sources": [{"url": "https://example.com/con", "title": "Con", "snippet": "c"}],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", side_effect=["pro text", "con text"]) as fetch_page:
            result = node_fetch_key_pages(state)

        self.assertEqual(result["fetch_budget_remaining"], 0)
        self.assertEqual(result["logs"], ["[fetch] attempted=2 accepted=2 remaining_fetch=0"])
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][0]["page_text"], "pro text")
        self.assertEqual(state["work"]["claim-1"]["con_sources"][0]["page_text"], "con text")
        self.assertTrue(state["work"]["claim-1"]["pro_sources"][0]["page_fetch_attempted"])
        self.assertTrue(state["work"]["claim-1"]["con_sources"][0]["page_fetch_attempted"])
        fetch_page.assert_any_call("https://example.com/pro")
        fetch_page.assert_any_call("https://example.com/con")

    def test_node_fetch_key_pages_fetches_duplicate_url_once_and_updates_both_sides(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 2,
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [{"url": "https://example.com/shared", "title": "Shared", "snippet": "shared"}],
                    "con_sources": [{"url": "https://example.com/shared", "title": "Shared", "snippet": "shared"}],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", return_value="shared text") as fetch_page:
            result = node_fetch_key_pages(state)

        self.assertEqual(result["logs"], ["[fetch] attempted=1 accepted=1 remaining_fetch=1"])
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][0]["page_text"], "shared text")
        self.assertEqual(state["work"]["claim-1"]["con_sources"][0]["page_text"], "shared text")
        fetch_page.assert_called_once_with("https://example.com/shared")

    def test_node_fetch_key_pages_does_not_retry_rejected_source(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 2,
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [{"url": "https://example.com/pro", "title": "Pro", "snippet": "p"}],
                    "con_sources": [],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", return_value=None) as fetch_page:
            first = node_fetch_key_pages(state)
            second = node_fetch_key_pages(state)

        self.assertEqual(first["logs"], ["[fetch] attempted=1 accepted=0 remaining_fetch=1"])
        self.assertEqual(second["logs"], ["[fetch] attempted=0 accepted=0 remaining_fetch=1"])
        self.assertTrue(state["work"]["claim-1"]["pro_sources"][0]["page_fetch_attempted"])
        self.assertIsNone(state["work"]["claim-1"]["pro_sources"][0]["page_text"])
        fetch_page.assert_called_once_with("https://example.com/pro")


if __name__ == "__main__":
    unittest.main()
