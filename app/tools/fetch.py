from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.request
from html import unescape
from typing import Optional
from urllib.parse import urlparse

from app.core.config import get_settings

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


_CACHE_LOCK = threading.Lock()


def _cache_dir() -> str:
    settings = get_settings()
    path = os.path.join(settings.data_dir, "cache", "fetch")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_key(url: str) -> str:
    return hashlib.sha256((url or "").strip().encode("utf-8")).hexdigest()


def _cache_path(url: str) -> str:
    return os.path.join(_cache_dir(), f"{_cache_key(url)}.json")


def _clip_text(text: str | None, max_chars: int) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    return text[:max_chars]


def _load_cached_text(url: str, max_chars: int) -> Optional[str]:
    settings = get_settings()
    if not settings.fetch_cache_enabled:
        return None

    path = _cache_path(url)
    if not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    created_at = float(payload.get("created_at", 0))
    if settings.fetch_cache_ttl_seconds > 0 and (time.time() - created_at) > settings.fetch_cache_ttl_seconds:
        return None
    return _clip_text(payload.get("text"), max_chars)


def _save_cached_text(url: str, text: str, content_type: str) -> None:
    settings = get_settings()
    if not settings.fetch_cache_enabled:
        return

    payload = {"created_at": time.time(), "content_type": content_type, "text": text}
    with _CACHE_LOCK:
        with open(_cache_path(url), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def _count_signal_metrics(text: str) -> tuple[int, int, int, int]:
    visible_chars = len(re.sub(r"\s+", "", text))
    signal_chars = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z]{2,}", text))
    han_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return visible_chars, signal_chars, latin_words, han_chars


def _filter_extracted_text(text: str | None, min_chars: int, min_ratio: float) -> Optional[str]:
    text = _normalize_whitespace(text or "")
    if not text:
        return None

    visible_chars, signal_chars, latin_words, han_chars = _count_signal_metrics(text)
    if visible_chars == 0:
        return None

    signal_ratio = signal_chars / visible_chars
    has_enough_language_signal = latin_words >= 8 or han_chars >= 20
    has_enough_length = visible_chars >= min_chars
    if not has_enough_length and not has_enough_language_signal:
        return None
    if signal_ratio < min_ratio:
        return None
    if not has_enough_language_signal:
        return None
    return text


def _decode_response_bytes(raw: bytes, headers) -> str:
    charset = None
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset()
    for encoding in [charset, "utf-8", "utf-8-sig", "gb18030", "latin-1"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_html_text(html: str) -> Optional[str]:
    cleaned = re.sub(r"(?is)<!--.*?-->", " ", html)
    cleaned = re.sub(r"(?is)<(script|style|noscript|svg|canvas|form|iframe).*?>.*?</\1>", " ", cleaned)
    cleaned = re.sub(r"(?is)<(nav|footer|header|aside).*?>.*?</\1>", " ", cleaned)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</(p|div|section|article|main|li|ul|ol|h[1-6]|tr|table|blockquote)>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    lines = [_normalize_whitespace(line) for line in cleaned.split("\n")]
    lines = [line for line in lines if line and len(line) > 1]
    text = "\n".join(lines)
    return _normalize_whitespace(text) or None


def _extract_pdf_text(raw: bytes) -> Optional[str]:
    if PdfReader is None:
        return None
    try:
        reader = PdfReader(io.BytesIO(raw))
        chunks = []
        for page in reader.pages[:8]:
            text = page.extract_text() or ""
            text = _normalize_whitespace(text)
            if text:
                chunks.append(text)
            if sum(len(chunk) for chunk in chunks) >= 12000:
                break
        merged = "\n\n".join(chunks)
        return _normalize_whitespace(merged) or None
    except Exception:
        return None


def _extract_text_content(raw: bytes, headers) -> Optional[str]:
    text = _decode_response_bytes(raw, headers)
    return _normalize_whitespace(unescape(text)) or None


def _detect_content_type(url: str, headers, raw: bytes) -> str:
    if headers is not None and hasattr(headers, "get_content_type"):
        content_type = (headers.get_content_type() or "").lower()
        if content_type:
            return content_type

    parsed = urlparse(url)
    if parsed.path.lower().endswith(".pdf") or raw.startswith(b"%PDF"):
        return "application/pdf"
    return "text/html"


def fetch_page_text(url: str, timeout_s: int = 10, max_chars: int = 3000) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None

    cached = _load_cached_text(url, max_chars)
    if cached is not None:
        return cached

    settings = get_settings()
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FactCheckMA/1.0)",
                "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read(settings.fetch_max_bytes)
            headers = getattr(resp, "headers", None)
            final_url = getattr(resp, "geturl", lambda: url)() or url

        content_type = _detect_content_type(final_url, headers, raw)
        if content_type == "application/pdf":
            text = _extract_pdf_text(raw)
        elif content_type.startswith("text/plain"):
            text = _extract_text_content(raw, headers)
        else:
            text = _extract_html_text(_decode_response_bytes(raw, headers))

        text = _filter_extracted_text(
            text,
            min_chars=settings.fetch_min_text_chars,
            min_ratio=settings.fetch_min_text_ratio,
        )
        text = _clip_text(text, max_chars)
        if text:
            _save_cached_text(url, text, content_type)
        return text
    except Exception:
        return None
