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
