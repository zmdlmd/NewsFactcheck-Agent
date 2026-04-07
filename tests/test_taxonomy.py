import unittest

from app.tools.taxonomy import normalize_rag_filters, normalize_taxonomy_metadata


class TaxonomyTests(unittest.TestCase):
    def test_normalize_rag_filters_maps_aliases_to_canonical_taxonomy(self):
        filters = {
            "language": "English",
            "type": "press release",
            "policy": "gov",
            "topic": "Space Exploration",
            "ignored": "",
        }

        normalized = normalize_rag_filters(filters)

        self.assertEqual(
            normalized,
            {
                "lang": ["en"],
                "category": ["announcement"],
                "source_policy": ["official"],
                "topic": ["space-exploration"],
            },
        )

    def test_normalize_taxonomy_metadata_infers_category_topic_region_and_policy(self):
        metadata = normalize_taxonomy_metadata(
            {"path": "finance/global/annual-report-2025.md", "source_name": "local-corpus"},
            title="Annual Report 2025",
            source_name="local-corpus",
            path="finance/global/annual-report-2025.md",
        )

        self.assertEqual(metadata["category"], "report")
        self.assertEqual(metadata["topic"], "finance")
        self.assertEqual(metadata["region"], "global")
        self.assertEqual(metadata["source_policy"], "institutional")


if __name__ == "__main__":
    unittest.main()
