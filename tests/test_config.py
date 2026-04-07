import os
import unittest
from unittest.mock import patch

from app.core.config import get_settings


class SettingsTests(unittest.TestCase):
    def test_get_settings_reads_environment_at_call_time(self):
        with patch.dict(
            os.environ,
            {
                "MODEL_NAME": "env-model",
                "MAX_CLAIMS": "7",
                "LLM_API_KEY": "env-key",
                "LLM_BASE_URL": "https://example.com/v1",
                "RETRIEVAL_MODE": "hybrid",
                "RAG_BACKEND": "qdrant",
                "RAG_COLLECTION": "test_collection",
                "RAG_TOP_K": "8",
                "RAG_SCORE_THRESHOLD": "0.42",
                "RERANK_MODE": "diversity",
                "RERANK_MAX_CANDIDATES": "11",
                "RERANK_DIVERSITY_WEIGHT": "4.5",
                "RETRIEVAL_DIAGNOSTICS_ENABLED": "0",
                "RAG_INDEX_DIR": "./tmp-rag-index",
                "RAG_DOCS_DIR": "./tmp-rag-docs",
                "EMBEDDING_MODEL": "test-embedding-model",
                "EMBEDDING_API_KEY": "embedding-key",
                "EMBEDDING_BASE_URL": "https://embeddings.example.com/v1",
                "SEARCH_BUDGET": "3",
                "MAX_ROUNDS_PER_CLAIM": "9",
                "SEARCH_CACHE_ENABLED": "0",
                "SEARCH_CACHE_TTL_SECONDS": "123",
                "ENABLE_FETCH": "1",
                "FETCH_BUDGET": "2",
                "FETCH_CACHE_ENABLED": "0",
                "FETCH_CACHE_TTL_SECONDS": "456",
                "FETCH_MAX_BYTES": "789",
                "FETCH_MIN_TEXT_CHARS": "33",
                "FETCH_MIN_TEXT_RATIO": "0.55",
                "DATA_DIR": "./tmp-data",
            },
            clear=False,
        ):
            settings = get_settings()

        self.assertEqual(settings.model_name, "env-model")
        self.assertEqual(settings.max_claims, 7)
        self.assertEqual(settings.llm_api_key, "env-key")
        self.assertEqual(settings.llm_base_url, "https://example.com/v1")
        self.assertEqual(settings.retrieval_mode, "hybrid")
        self.assertEqual(settings.rag_backend, "qdrant")
        self.assertEqual(settings.rag_collection, "test_collection")
        self.assertEqual(settings.rag_top_k, 8)
        self.assertEqual(settings.rag_score_threshold, 0.42)
        self.assertEqual(settings.rerank_mode, "diversity")
        self.assertEqual(settings.rerank_max_candidates, 11)
        self.assertEqual(settings.rerank_diversity_weight, 4.5)
        self.assertFalse(settings.retrieval_diagnostics_enabled)
        self.assertEqual(settings.rag_index_dir, "./tmp-rag-index")
        self.assertEqual(settings.rag_docs_dir, "./tmp-rag-docs")
        self.assertEqual(settings.embedding_model, "test-embedding-model")
        self.assertEqual(settings.embedding_api_key, "embedding-key")
        self.assertEqual(settings.embedding_base_url, "https://embeddings.example.com/v1")
        self.assertEqual(settings.search_budget, 3)
        self.assertEqual(settings.max_rounds_per_claim, 9)
        self.assertFalse(settings.search_cache_enabled)
        self.assertEqual(settings.search_cache_ttl_seconds, 123)
        self.assertTrue(settings.enable_fetch)
        self.assertEqual(settings.fetch_budget, 2)
        self.assertFalse(settings.fetch_cache_enabled)
        self.assertEqual(settings.fetch_cache_ttl_seconds, 456)
        self.assertEqual(settings.fetch_max_bytes, 789)
        self.assertEqual(settings.fetch_min_text_chars, 33)
        self.assertEqual(settings.fetch_min_text_ratio, 0.55)
        self.assertEqual(settings.data_dir, "./tmp-data")


if __name__ == "__main__":
    unittest.main()
