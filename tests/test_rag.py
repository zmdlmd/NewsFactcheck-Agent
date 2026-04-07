import unittest
from unittest.mock import patch

from qdrant_client import QdrantClient

from app.core.config import Settings
from app.tools.rag import index_documents, rag_search


class FakeEmbeddings:
    @staticmethod
    def _embed(text: str) -> list[float]:
        lowered = (text or "").lower()
        return [
            1.0 if "earth" in lowered else 0.0,
            1.0 if "sun" in lowered else 0.0,
            1.0 if "mars" in lowered else 0.0,
        ]

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


class RagTests(unittest.TestCase):
    def test_index_documents_and_search_round_trip(self):
        settings = Settings(
            retrieval_mode="rag",
            rag_backend="qdrant",
            rag_collection="test_collection",
            rag_index_dir=":memory:",
            embedding_model="fake-embedding",
        )
        client = QdrantClient(path=":memory:")
        documents = [
            {
                "doc_id": "doc-earth",
                "chunk_id": "chunk-0",
                "title": "Earth Fact",
                "page_text": "Earth orbits the Sun once every year.",
                "source_name": "local-corpus",
                "metadata": {"lang": "en"},
            },
            {
                "doc_id": "doc-mars",
                "chunk_id": "chunk-0",
                "title": "Mars Fact",
                "page_text": "Mars has two small moons.",
                "source_name": "local-corpus",
                "metadata": {"lang": "en"},
            },
        ]

        with (
            patch("app.tools.rag.get_settings", return_value=settings),
            patch("app.tools.rag._build_qdrant_client", return_value=client),
            patch("app.tools.rag._build_embeddings", return_value=FakeEmbeddings()),
        ):
            indexed = index_documents(documents, recreate=True)
            hits = rag_search("earth sun", top_k=1)

        self.assertEqual(indexed, 2)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["doc_id"], "doc-earth")
        self.assertEqual(hits[0]["chunk_id"], "chunk-0")
        self.assertEqual(hits[0]["source_type"], "rag")
        self.assertEqual(hits[0]["url"], "rag://doc-earth/chunk-0")
        self.assertIn("Earth orbits the Sun", hits[0]["page_text"])

    def test_rag_search_normalizes_alias_filters_against_taxonomy(self):
        settings = Settings(
            retrieval_mode="rag",
            rag_backend="qdrant",
            rag_collection="test_collection_filters",
            rag_index_dir=":memory:",
            embedding_model="fake-embedding",
        )
        client = QdrantClient(path=":memory:")
        documents = [
            {
                "doc_id": "doc-announcement",
                "chunk_id": "chunk-0",
                "title": "Earth Announcement",
                "page_text": "Earth mission announcement from the official space agency.",
                "source_name": "space-agency",
                "metadata": {"language": "English", "type": "press release", "policy": "gov"},
            },
            {
                "doc_id": "doc-report",
                "chunk_id": "chunk-0",
                "title": "Earth Report",
                "page_text": "Earth mission annual report with tables and background.",
                "source_name": "space-agency",
                "metadata": {"language": "English", "type": "annual report", "policy": "gov"},
            },
        ]

        with (
            patch("app.tools.rag.get_settings", return_value=settings),
            patch("app.tools.rag._build_qdrant_client", return_value=client),
            patch("app.tools.rag._build_embeddings", return_value=FakeEmbeddings()),
        ):
            index_documents(documents, recreate=True)
            hits = rag_search("earth mission", top_k=5, filters={"language": "English", "type": "press release"})

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["doc_id"], "doc-announcement")
        self.assertEqual(hits[0]["metadata"]["lang"], "en")
        self.assertEqual(hits[0]["metadata"]["category"], "announcement")
        self.assertEqual(hits[0]["metadata"]["source_policy"], "official")

    def test_rag_search_supports_multi_value_filters(self):
        settings = Settings(
            retrieval_mode="rag",
            rag_backend="qdrant",
            rag_collection="test_collection_multivalue",
            rag_index_dir=":memory:",
            embedding_model="fake-embedding",
        )
        client = QdrantClient(path=":memory:")
        documents = [
            {
                "doc_id": "doc-en",
                "chunk_id": "chunk-0",
                "title": "Earth Report EN",
                "page_text": "Earth orbit report in English.",
                "source_name": "space-agency",
                "metadata": {"lang": "en", "category": "report"},
            },
            {
                "doc_id": "doc-zh",
                "chunk_id": "chunk-0",
                "title": "Earth Report ZH",
                "page_text": "Earth orbit report translated to Chinese.",
                "source_name": "space-agency",
                "metadata": {"lang": "zh", "category": "report"},
            },
        ]

        with (
            patch("app.tools.rag.get_settings", return_value=settings),
            patch("app.tools.rag._build_qdrant_client", return_value=client),
            patch("app.tools.rag._build_embeddings", return_value=FakeEmbeddings()),
        ):
            index_documents(documents, recreate=True)
            hits = rag_search("earth orbit", top_k=5, filters={"lang": ["en", "zh"], "category": ["report"]})

        self.assertEqual(len(hits), 2)


if __name__ == "__main__":
    unittest.main()
