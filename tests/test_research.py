import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.agent.node_handlers.research import node_fetch_key_pages, node_pro_search


class ResearchNodeTests(unittest.TestCase):
    def test_node_pro_search_passes_rag_filters_to_retrieval(self):
        state = {
            "search_budget_remaining": 2,
            "active_claim_id": "claim-1",
            "supervisor_plan": {"run_pro": True},
            "pro_plan": {
                "query": "space claim",
                "include_domains": ["nasa.gov"],
                "exclude_domains": ["reddit.com"],
                "rag_filters": {"lang": "en", "topic": "space"},
            },
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [],
                    "con_sources": [],
                    "judgement": None,
                }
            },
        }

        with (
            patch(
                "app.agent.node_handlers.research.retrieve_sources_detailed",
                return_value=(
                    [
                        {
                            "title": "Internal Space Note",
                            "url": "rag://doc-space/chunk-0",
                            "snippet": "space",
                            "page_text": "space",
                            "source_type": "rag",
                            "doc_id": "doc-space",
                            "chunk_id": "chunk-0",
                            "metadata": {},
                        }
                    ],
                    {
                        "mode": "hybrid",
                        "rag_filters": {"lang": ["en"], "topic": ["space"]},
                        "rerank_mode": "off",
                        "used_rerank": False,
                        "counts": {"rag": 1, "web": 0, "merged": 1, "returned": 1},
                    },
                ),
            ) as retrieve_sources_detailed,
            patch(
                "app.agent.node_handlers.research.get_settings",
                return_value=Settings(retrieval_diagnostics_enabled=True),
            ),
        ):
            result = node_pro_search(state)

        self.assertEqual(result["logs"][0], "[pro_search] +1 remaining=1")
        self.assertIn("[pro_search.diagnostics] mode=hybrid", result["logs"][1])
        self.assertIn("filters=lang=en; topic=space", result["logs"][1])
        self.assertEqual(result["retrieval_diagnostics"][0]["side"], "pro")
        self.assertEqual(result["retrieval_diagnostics"][0]["query"], "space claim")
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][0]["source_type"], "rag")
        retrieve_sources_detailed.assert_called_once_with(
            "space claim",
            claim_text="",
            include_domains=["nasa.gov"],
            exclude_domains=["reddit.com"],
            max_results=5,
            rag_filters={"lang": "en", "topic": "space"},
        )

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

    def test_node_fetch_key_pages_skips_rag_sources(self):
        state = {
            "enable_fetch": True,
            "fetch_budget_remaining": 2,
            "active_claim_id": "claim-1",
            "supervisor_plan": {"use_fetch": True},
            "work": {
                "claim-1": {
                    "rounds": 0,
                    "pro_sources": [
                        {
                            "url": "rag://doc-earth/chunk-0",
                            "title": "Earth Fact",
                            "snippet": "Earth orbits the Sun.",
                            "page_text": "Earth orbits the Sun.",
                            "source_type": "rag",
                            "doc_id": "doc-earth",
                            "chunk_id": "chunk-0",
                        }
                    ],
                    "con_sources": [
                        {
                            "url": "https://example.com/web-source",
                            "title": "Web Source",
                            "snippet": "A web source with additional context.",
                            "source_type": "web",
                        }
                    ],
                    "judgement": None,
                }
            },
        }

        with patch("app.agent.node_handlers.research.fetch_page_text", return_value="web text") as fetch_page:
            result = node_fetch_key_pages(state)

        self.assertEqual(result["logs"], ["[fetch] attempted=1 accepted=1 remaining_fetch=1"])
        self.assertEqual(state["work"]["claim-1"]["pro_sources"][0]["page_text"], "Earth orbits the Sun.")
        self.assertEqual(state["work"]["claim-1"]["con_sources"][0]["page_text"], "web text")
        fetch_page.assert_called_once_with("https://example.com/web-source")


if __name__ == "__main__":
    unittest.main()
