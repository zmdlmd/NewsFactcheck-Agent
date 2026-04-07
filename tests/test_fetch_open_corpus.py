from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_open_corpus.py"
_SPEC = importlib.util.spec_from_file_location("fetch_open_corpus", _SCRIPT_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)


class FetchOpenCorpusTests(unittest.TestCase):
    def test_html_to_text_strips_markup_and_keeps_content(self):
        text = _MODULE._html_to_text("<h1>Earth</h1><p>Earth orbits the <b>Sun</b>.</p>")

        self.assertIn("Earth", text)
        self.assertIn("Earth orbits the Sun.", text)
        self.assertNotIn("<b>", text)

    def test_world_bank_markdown_renders_recent_values(self):
        markdown = _MODULE._world_bank_markdown(
            {
                "id": "SP.POP.TOTL",
                "name": "Population, total",
                "source": {"value": "World Development Indicators"},
                "sourceNote": "Total population is based on the de facto definition of population.",
                "sourceOrganization": "World Bank staff estimates.",
                "topics": [{"value": "Health"}],
            },
            [
                {"country": {"value": "World"}, "date": "2024", "value": 8000000000},
                {"country": {"value": "World"}, "date": "2023", "value": 7900000000},
            ],
            countries=["WLD"],
        )

        self.assertIn("# Population, total (SP.POP.TOTL)", markdown)
        self.assertIn("Source: World Bank Indicators API", markdown)
        self.assertIn("## Recent Values", markdown)
        self.assertIn("- 2024: 8,000,000,000", markdown)


if __name__ == "__main__":
    unittest.main()
