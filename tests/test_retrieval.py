import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.tools.retrieval import retrieve_sources, retrieve_sources_detailed


class RetrievalTests(unittest.TestCase):
    def test_retrieve_sources_web_mode_annotates_results(self):
        settings = Settings(retrieval_mode="web")
        raw_results = [
            {
                "title": "NASA",
                "url": "https://www.nasa.gov/earth-orbit",
                "snippet": "Official explanation.",
            }
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.tavily_search", return_value=raw_results),
        ):
            results = retrieve_sources("earth orbit")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_type"], "web")
        self.assertEqual(results[0]["source_name"], "www.nasa.gov")
        self.assertEqual(results[0]["url"], "https://www.nasa.gov/earth-orbit")

    def test_retrieve_sources_rag_mode_uses_rag_only(self):
        settings = Settings(retrieval_mode="rag", rag_top_k=3)
        rag_results = [
            {
                "title": "Internal Note",
                "url": "rag://doc-1/chunk-0",
                "snippet": "internal evidence",
                "page_text": "internal evidence",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.91,
                "metadata": {"team": "research"},
            }
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results) as rag_search,
            patch("app.tools.retrieval.tavily_search") as tavily_search,
        ):
            results = retrieve_sources("internal claim")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_type"], "rag")
        rag_search.assert_called_once()
        tavily_search.assert_not_called()

    def test_retrieve_sources_hybrid_merges_and_ranks_rag_hits(self):
        settings = Settings(retrieval_mode="hybrid", rag_top_k=2)
        rag_results = [
            {
                "title": "Internal Report",
                "url": "rag://doc-1/chunk-0",
                "snippet": "high-confidence internal evidence",
                "page_text": "high-confidence internal evidence",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.93,
                "metadata": {},
            }
        ]
        web_results = [
            {
                "title": "Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Earth",
                "snippet": "A user-editable encyclopedia entry.",
            }
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=web_results),
        ):
            results = retrieve_sources("earth orbit", max_results=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["source_type"], "rag")
        self.assertEqual(results[1]["source_type"], "web")

    def test_retrieve_sources_hybrid_prefers_report_like_rag_source_for_numeric_claim(self):
        settings = Settings(retrieval_mode="hybrid", rag_top_k=2)
        rag_results = [
            {
                "title": "Internal Memo",
                "url": "rag://doc-1/chunk-0",
                "snippet": "General business background.",
                "page_text": "General business background.",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.89,
                "metadata": {"lang": "en", "category": "reference"},
            },
            {
                "title": "Annual Report 2025",
                "url": "rag://doc-2/chunk-0",
                "snippet": "Revenue table and financial statistics.",
                "page_text": "Revenue reached $5 billion in 2025 according to the annual report.",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-2",
                "chunk_id": "chunk-0",
                "score": 0.82,
                "metadata": {"lang": "en", "category": "report"},
            },
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=[]),
        ):
            results = retrieve_sources(
                "company revenue",
                claim_text="The company reported revenue of $5 billion in 2025.",
                max_results=2,
            )

        self.assertEqual(results[0]["doc_id"], "doc-2")
        self.assertEqual(results[1]["doc_id"], "doc-1")

    def test_retrieve_sources_hybrid_prefers_news_like_source_for_temporal_claim(self):
        settings = Settings(retrieval_mode="hybrid", rag_top_k=2)
        rag_results = [
            {
                "title": "Governance Report",
                "url": "rag://doc-1/chunk-0",
                "snippet": "General governance report.",
                "page_text": "A governance report with historical background.",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.83,
                "metadata": {"lang": "en", "category": "report"},
            },
            {
                "title": "CEO Announcement",
                "url": "rag://doc-2/chunk-0",
                "snippet": "Official announcement about the newly appointed CEO in 2026.",
                "page_text": "The company announced a new CEO in 2026.",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-2",
                "chunk_id": "chunk-0",
                "score": 0.78,
                "metadata": {"lang": "en", "category": "announcement"},
            },
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=[]),
        ):
            results = retrieve_sources(
                "company ceo",
                claim_text="The company announced a new CEO in 2026.",
                max_results=2,
            )

        self.assertEqual(results[0]["doc_id"], "doc-2")
        self.assertEqual(results[1]["doc_id"], "doc-1")

    def test_retrieve_sources_hybrid_uses_taxonomy_and_lexical_overlap_in_rerank(self):
        settings = Settings(retrieval_mode="hybrid", rag_top_k=2)
        rag_results = [
            {
                "title": "Space Forum Thread",
                "url": "rag://doc-1/chunk-0",
                "snippet": "General discussion about planets.",
                "page_text": "Community discussion about planets and space travel.",
                "source_type": "rag",
                "source_name": "community-board",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.84,
                "metadata": {"lang": "en", "source_policy": "community", "category": "reference"},
            },
            {
                "title": "Earth Orbit Report",
                "url": "rag://doc-2/chunk-0",
                "snippet": "Earth orbits the Sun once every year.",
                "page_text": "Earth orbits the Sun once every year according to the official agency report.",
                "source_type": "rag",
                "source_name": "space-agency",
                "doc_id": "doc-2",
                "chunk_id": "chunk-0",
                "score": 0.79,
                "metadata": {"lang": "en", "source_policy": "official", "category": "report"},
            },
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=[]),
        ):
            results = retrieve_sources(
                "earth orbit",
                claim_text="Earth orbits the Sun once every year.",
                max_results=2,
            )

        self.assertEqual(results[0]["doc_id"], "doc-2")
        self.assertEqual(results[1]["doc_id"], "doc-1")

    def test_retrieve_sources_detailed_returns_diagnostics(self):
        settings = Settings(retrieval_mode="hybrid", rag_top_k=2, retrieval_diagnostics_enabled=True)
        rag_results = [
            {
                "title": "Internal Report",
                "url": "rag://doc-1/chunk-0",
                "snippet": "high-confidence internal evidence",
                "page_text": "high-confidence internal evidence",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.93,
                "metadata": {"lang": "en", "category": "report"},
            }
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=[]),
        ):
            results, diagnostics = retrieve_sources_detailed(
                "earth orbit",
                claim_text="Earth orbits the Sun.",
                max_results=1,
                rag_filters={"lang": ["en", "zh"], "category": "report"},
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(diagnostics["mode"], "hybrid")
        self.assertEqual(diagnostics["counts"]["rag"], 1)
        self.assertEqual(diagnostics["counts"]["returned"], 1)
        self.assertEqual(diagnostics["rag_filters"], {"lang": ["en", "zh"], "category": ["report"]})
        self.assertEqual(diagnostics["top_results"][0]["source_type"], "rag")

    def test_retrieve_sources_hybrid_diversity_rerank_can_promote_source_diversity(self):
        settings = Settings(
            retrieval_mode="hybrid",
            rag_top_k=3,
            rerank_mode="diversity",
            rerank_max_candidates=3,
            rerank_diversity_weight=8.0,
        )
        rag_results = [
            {
                "title": "NASA Orbit Report",
                "url": "rag://doc-1/chunk-0",
                "snippet": "Earth orbits the Sun with official scientific context.",
                "page_text": "Earth orbits the Sun with official scientific context.",
                "source_type": "rag",
                "source_name": "nasa",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.88,
                "metadata": {"lang": "en", "category": "report", "source_policy": "official"},
            },
            {
                "title": "NASA Orbit Briefing",
                "url": "rag://doc-2/chunk-0",
                "snippet": "Earth orbit briefing from the same source.",
                "page_text": "Earth orbit briefing from the same source.",
                "source_type": "rag",
                "source_name": "nasa",
                "doc_id": "doc-2",
                "chunk_id": "chunk-0",
                "score": 0.87,
                "metadata": {"lang": "en", "category": "report", "source_policy": "official"},
            },
        ]
        web_results = [
            {
                "title": "ESA Orbit Explainer",
                "url": "https://www.esa.int/earth-orbit",
                "snippet": "Official ESA explanation of Earth's orbit around the Sun.",
            }
        ]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=web_results),
        ):
            results = retrieve_sources(
                "earth orbit",
                claim_text="Earth orbits the Sun.",
                max_results=2,
            )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["source_name"], "nasa")
        self.assertEqual(results[1]["source_type"], "web")

    def test_retrieve_sources_hybrid_llm_rerank_reorders_candidates(self):
        settings = Settings(
            retrieval_mode="hybrid",
            rag_top_k=3,
            rerank_mode="llm",
            rerank_max_candidates=3,
            retrieval_diagnostics_enabled=True,
        )
        rag_results = [
            {
                "title": "Internal Memo",
                "url": "rag://doc-1/chunk-0",
                "snippet": "General background memo.",
                "page_text": "General background memo.",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-1",
                "chunk_id": "chunk-0",
                "score": 0.89,
                "metadata": {"lang": "en", "category": "reference"},
            },
            {
                "title": "Annual Report 2025",
                "url": "rag://doc-2/chunk-0",
                "snippet": "Revenue table and financial statistics.",
                "page_text": "Revenue reached $5 billion in 2025 according to the annual report.",
                "source_type": "rag",
                "source_name": "internal-kb",
                "doc_id": "doc-2",
                "chunk_id": "chunk-0",
                "score": 0.82,
                "metadata": {"lang": "en", "category": "report"},
            },
        ]

        class FakeRerank:
            ordered_ids = ["c2", "c1"]

        with (
            patch("app.tools.retrieval.get_settings", return_value=settings),
            patch("app.tools.retrieval.rag_search", return_value=rag_results),
            patch("app.tools.retrieval.tavily_search", return_value=[]),
            patch("app.tools.retrieval.build_model", return_value=object()),
            patch("app.tools.retrieval.invoke_structured", return_value=FakeRerank()),
        ):
            results, diagnostics = retrieve_sources_detailed(
                "company revenue",
                claim_text="The company reported revenue of $5 billion in 2025.",
                max_results=2,
            )

        self.assertEqual(results[0]["doc_id"], "doc-2")
        self.assertTrue(diagnostics["used_rerank"])
        self.assertEqual(diagnostics["rerank_mode"], "llm")


if __name__ == "__main__":
    unittest.main()
