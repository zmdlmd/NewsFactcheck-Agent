import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.tools.search import normalize_results, tavily_search


class FakeTavilySearch:
    def __init__(self, max_results, topic):
        self.max_results = max_results
        self.topic = topic

    def invoke(self, args):
        return {
            "results": [
                {
                    "title": "Wikipedia Result",
                    "url": "https://en.wikipedia.org/wiki/Earth",
                    "content": "A user-editable encyclopedia entry.",
                },
                {
                    "title": "NASA Result",
                    "url": "https://www.nasa.gov/earth-orbit",
                    "content": "Official NASA explanation of Earth's orbit around the Sun.",
                },
                {
                    "title": "University Result",
                    "url": "https://astro.university.edu/orbits",
                    "content": "University course notes about heliocentric orbits.",
                },
                {
                    "title": "Second NASA Result",
                    "url": "https://www.nasa.gov/earth-orbit-faq",
                    "content": "Another official NASA page.",
                },
            ]
        }


class SearchTests(unittest.TestCase):
    def test_normalize_results_canonicalizes_urls(self):
        raw = {
            "results": [
                {"title": "A", "url": "HTTPS://Example.com/path/", "content": "x"},
                {"title": "B", "url": "", "content": "y"},
            ]
        }

        normalized = normalize_results(raw, max_keep=None)

        self.assertEqual(
            normalized,
            [{"title": "A", "url": "https://example.com/path", "snippet": "x"}],
        )

    def test_tavily_search_prefers_authoritative_and_diverse_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(data_dir=tmpdir, search_cache_enabled=False)
            with (
                patch("app.tools.search.get_settings", return_value=settings),
                patch("app.tools.search.TavilySearch", FakeTavilySearch),
            ):
                results = tavily_search("earth orbit", max_results=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["url"], "https://www.nasa.gov/earth-orbit")
        self.assertEqual(results[1]["url"], "https://astro.university.edu/orbits")
        self.assertEqual(results[2]["url"], "https://en.wikipedia.org/wiki/Earth")

    def test_tavily_search_uses_persistent_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                data_dir=tmpdir,
                search_cache_enabled=True,
                search_cache_ttl_seconds=3600,
            )
            first_tool = FakeTavilySearch(max_results=5, topic="general")
            second_tool = FakeTavilySearch(max_results=5, topic="general")
            second_tool.invoke = unittest.mock.Mock(side_effect=AssertionError("cache was not used"))

            with (
                patch("app.tools.search.get_settings", return_value=settings),
                patch("app.tools.search.TavilySearch", side_effect=[first_tool, second_tool]),
            ):
                first = tavily_search("earth orbit", max_results=2)
                second = tavily_search("earth orbit", max_results=2)

            self.assertEqual(first, second)
            cache_dir = os.path.join(tmpdir, "cache", "search")
            files = os.listdir(cache_dir)
            self.assertEqual(len(files), 1)
            with open(os.path.join(cache_dir, files[0]), "r", encoding="utf-8") as f:
                cached = json.load(f)
            self.assertEqual(len(cached["results"]), 2)


if __name__ == "__main__":
    unittest.main()
