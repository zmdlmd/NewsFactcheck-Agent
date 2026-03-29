import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.tools.fetch import fetch_page_text


class FakeHeaders:
    def __init__(self, content_type: str = "text/html", charset: str | None = "utf-8"):
        self._content_type = content_type
        self._charset = charset

    def get_content_type(self):
        return self._content_type

    def get_content_charset(self):
        return self._charset


class FakeResponse:
    def __init__(self, body: bytes, *, content_type: str = "text/html", charset: str | None = "utf-8", final_url: str = "https://example.com/article"):
        self._body = body
        self.headers = FakeHeaders(content_type=content_type, charset=charset)
        self._final_url = final_url

    def read(self, max_bytes: int | None = None):
        if max_bytes is None:
            return self._body
        return self._body[:max_bytes]

    def geturl(self):
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FetchTests(unittest.TestCase):
    def test_fetch_page_text_extracts_html_body_text(self):
        html = b"""
        <html>
          <head><title>Example</title><script>bad()</script></head>
          <body>
            <nav>Navigation</nav>
            <main>
              <h1>Earth Orbits the Sun</h1>
              <p>The Earth revolves around the Sun once every year.</p>
            </main>
          </body>
        </html>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                data_dir=tmpdir,
                fetch_cache_enabled=False,
                fetch_max_bytes=4096,
                fetch_min_text_chars=40,
                fetch_min_text_ratio=0.4,
            )
            with (
                patch("app.tools.fetch.get_settings", return_value=settings),
                patch("app.tools.fetch.urllib.request.urlopen", return_value=FakeResponse(html)),
            ):
                text = fetch_page_text("https://example.com/article")

        self.assertIn("Earth Orbits the Sun", text)
        self.assertIn("The Earth revolves around the Sun once every year.", text)
        self.assertNotIn("Navigation", text)
        self.assertNotIn("bad()", text)

    def test_fetch_page_text_handles_text_plain(self):
        body = (
            "Earth orbits the Sun once every year.\n"
            "Astronomy textbooks describe this as a heliocentric orbit.\n"
            "This plain text file contains enough real language content to keep.\n"
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                data_dir=tmpdir,
                fetch_cache_enabled=False,
                fetch_max_bytes=4096,
                fetch_min_text_chars=40,
                fetch_min_text_ratio=0.4,
            )
            with (
                patch("app.tools.fetch.get_settings", return_value=settings),
                patch(
                    "app.tools.fetch.urllib.request.urlopen",
                    return_value=FakeResponse(body, content_type="text/plain", final_url="https://example.com/file.txt"),
                ),
            ):
                text = fetch_page_text("https://example.com/file.txt")

        self.assertIn("Earth orbits the Sun once every year.", text)

    def test_fetch_page_text_uses_persistent_cache(self):
        html = (
            b"<html><body><p>"
            b"This cached page contains enough real language content to pass the fetch quality filter."
            b"</p></body></html>"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                data_dir=tmpdir,
                fetch_cache_enabled=True,
                fetch_cache_ttl_seconds=3600,
                fetch_max_bytes=4096,
                fetch_min_text_chars=10,
                fetch_min_text_ratio=0.3,
            )

            with (
                patch("app.tools.fetch.get_settings", return_value=settings),
                patch("app.tools.fetch.urllib.request.urlopen", return_value=FakeResponse(html)),
            ):
                first = fetch_page_text("https://example.com/cache")

            with (
                patch("app.tools.fetch.get_settings", return_value=settings),
                patch(
                    "app.tools.fetch.urllib.request.urlopen",
                    side_effect=AssertionError("network should not be used when cache exists"),
                ),
            ):
                second = fetch_page_text("https://example.com/cache")

            self.assertEqual(first, second)
            cache_dir = os.path.join(tmpdir, "cache", "fetch")
            files = os.listdir(cache_dir)
            self.assertEqual(len(files), 1)
            with open(os.path.join(cache_dir, files[0]), "r", encoding="utf-8") as f:
                cached = json.load(f)

        self.assertIn("enough real language content", cached["text"])
        self.assertEqual(cached["content_type"], "text/html")

    def test_fetch_page_text_uses_pdf_extractor_for_pdf_content(self):
        raw = b"%PDF-1.7 fake"

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                data_dir=tmpdir,
                fetch_cache_enabled=False,
                fetch_max_bytes=4096,
                fetch_min_text_chars=10,
                fetch_min_text_ratio=0.3,
            )
            with (
                patch("app.tools.fetch.get_settings", return_value=settings),
                patch(
                    "app.tools.fetch.urllib.request.urlopen",
                    return_value=FakeResponse(raw, content_type="application/pdf", final_url="https://example.com/file.pdf"),
                ),
                patch(
                    "app.tools.fetch._extract_pdf_text",
                    return_value="Extracted PDF text with enough real language content to pass the fetch quality filter.",
                ) as extract_pdf,
            ):
                text = fetch_page_text("https://example.com/file.pdf")

        self.assertIn("enough real language content", text)
        extract_pdf.assert_called_once_with(raw)

    def test_fetch_page_text_rejects_short_or_low_signal_content(self):
        html = b"<html><body><div>Home</div><div>Login</div><div>Menu</div></body></html>"

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                data_dir=tmpdir,
                fetch_cache_enabled=False,
                fetch_max_bytes=4096,
                fetch_min_text_chars=80,
                fetch_min_text_ratio=0.45,
            )
            with (
                patch("app.tools.fetch.get_settings", return_value=settings),
                patch("app.tools.fetch.urllib.request.urlopen", return_value=FakeResponse(html)),
            ):
                text = fetch_page_text("https://example.com/noisy")

        self.assertIsNone(text)


if __name__ == "__main__":
    unittest.main()
