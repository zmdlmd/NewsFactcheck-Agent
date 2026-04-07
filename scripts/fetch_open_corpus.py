from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from app.core.config import get_settings


_DEFAULT_MANIFEST = Path(__file__).with_name("open_corpus_manifest.json")
_USER_AGENT = "NewsFactcheck-Agent/0.1 (open-corpus bootstrap)"
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "main",
    "ul",
    "ol",
    "li",
    "table",
    "tr",
    "td",
    "th",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
}


class _HTMLToTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)
            self.parts.append(" ")

    def text(self) -> str:
        text = unescape("".join(self.parts))
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        return text.strip()


def _html_to_text(html: str) -> str:
    parser = _HTMLToTextParser()
    parser.feed(html or "")
    parser.close()
    return parser.text()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return value.strip("-") or "item"


def _http_get_json(url: str) -> Any:
    req = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Api-User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _wikipedia_markdown(entry: dict[str, Any], *, title: str, lang: str) -> str:
    license_info = entry.get("license") or {}
    page_url = f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
    api_url = f"https://{lang}.wikipedia.org/w/rest.php/v1/page/{quote(title, safe='')}/with_html"
    description = (entry.get("description") or "").strip()
    text = _html_to_text(entry.get("html") or "")

    lines = [
        f"# {entry.get('title') or title}",
        "",
        "Source: Wikipedia",
        f"Language: {lang}",
        f"Page URL: {page_url}",
        f"API URL: {api_url}",
        f"License: {(license_info.get('title') or 'see page metadata').strip()}",
    ]
    if license_info.get("url"):
        lines.append(f"License URL: {license_info['url']}")
    if entry.get("latest", {}).get("timestamp"):
        lines.append(f"Latest Revision Timestamp: {entry['latest']['timestamp']}")
    lines.extend(
        [
            f"Retrieved At: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
    )
    if description:
        lines.extend(["## Description", "", description, ""])
    lines.extend(["## Content", "", text])
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:,.0f}"
        if abs(value) >= 1:
            return f"{value:,.2f}"
        return f"{value:.4f}"
    return str(value)


def _world_bank_markdown(
    indicator_meta: dict[str, Any],
    observations: list[dict[str, Any]],
    *,
    countries: list[str],
) -> str:
    indicator_id = indicator_meta.get("id") or "unknown-indicator"
    title = indicator_meta.get("name") or indicator_id
    api_url = f"https://api.worldbank.org/v2/country/{';'.join(countries)}/indicator/{indicator_id}?format=json"
    source_name = ((indicator_meta.get("source") or {}).get("value") or "World Bank").strip()
    source_note = (indicator_meta.get("sourceNote") or "").strip()
    source_org = (indicator_meta.get("sourceOrganization") or "").strip()
    topics = [topic.get("value") for topic in (indicator_meta.get("topics") or []) if topic.get("value")]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in observations:
        country_name = ((row.get("country") or {}).get("value") or row.get("countryiso3code") or "Unknown").strip()
        if row.get("value") is None:
            continue
        grouped.setdefault(country_name, []).append(row)

    lines = [
        f"# {title} ({indicator_id})",
        "",
        "Source: World Bank Indicators API",
        f"API URL: {api_url}",
        "License: CC BY 4.0",
        "License URL: https://datacatalog1.worldbank.org/public-licenses",
        f"Retrieved At: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"## Source",
        "",
        source_name,
        "",
    ]
    if topics:
        lines.extend(["## Topics", "", ", ".join(topics), ""])
    if source_note:
        lines.extend(["## Indicator Description", "", source_note, ""])
    if source_org:
        lines.extend(["## Source Organization", "", source_org, ""])

    lines.extend(["## Recent Values", ""])
    for country_name in sorted(grouped):
        rows = sorted(grouped[country_name], key=lambda item: item.get("date") or "", reverse=True)
        lines.append(f"### {country_name}")
        lines.append("")
        for row in rows:
            lines.append(f"- {row.get('date')}: {_format_value(row.get('value'))}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _fetch_wikipedia_corpus(manifest: dict[str, Any], out_dir: Path) -> int:
    wikipedia = manifest.get("wikipedia") or {}
    lang = str(wikipedia.get("lang") or "en").strip() or "en"
    titles = [str(title).strip() for title in wikipedia.get("titles") or [] if str(title).strip()]
    written = 0
    for title in titles:
        url = f"https://{lang}.wikipedia.org/w/rest.php/v1/page/{quote(title, safe='')}/with_html"
        entry = _http_get_json(url)
        path = out_dir / "open" / "reference" / "wikipedia" / lang / f"{_slug(title)}.md"
        _write_text(path, _wikipedia_markdown(entry, title=title, lang=lang))
        written += 1
        print(f"[wikipedia] wrote {path}")
    return written


def _fetch_world_bank_corpus(manifest: dict[str, Any], out_dir: Path) -> int:
    world_bank = manifest.get("world_bank") or {}
    countries = [str(code).strip().upper() for code in world_bank.get("countries") or [] if str(code).strip()]
    indicators = [str(code).strip() for code in world_bank.get("indicators") or [] if str(code).strip()]
    mrv = int(world_bank.get("mrv") or 6)
    written = 0

    if not countries:
        countries = ["WLD", "USA", "CHN", "IND"]

    for indicator in indicators:
        indicator_path = quote(indicator, safe=".")
        try:
            meta = _http_get_json(f"https://api.worldbank.org/v2/indicator/{indicator_path}?format=json")
            meta_rows = meta[1] if isinstance(meta, list) and len(meta) > 1 else []
            if not meta_rows:
                print(f"[world-bank] skipped {indicator}: no metadata")
                continue
            indicator_meta = meta_rows[0]

            data = _http_get_json(
                f"https://api.worldbank.org/v2/country/{';'.join(countries)}/indicator/{indicator_path}?format=json&per_page=200&mrv={mrv}"
            )
            observations = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
            path = out_dir / "open" / "official" / "data" / "world-bank" / f"{_slug(indicator)}.md"
            _write_text(path, _world_bank_markdown(indicator_meta, observations, countries=countries))
            written += 1
            print(f"[world-bank] wrote {path}")
        except Exception as exc:
            print(f"[world-bank] skipped {indicator}: {exc.__class__.__name__}: {exc}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a starter open-data corpus for local RAG")
    parser.add_argument(
        "--manifest",
        default=str(_DEFAULT_MANIFEST),
        help="Path to a JSON manifest describing Wikipedia titles and World Bank indicators",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=["wikipedia", "worldbank", "all"],
        default=["all"],
    )
    parser.add_argument("--out-dir", default=None, help="Override RAG_DOCS_DIR")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    settings = get_settings()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir or settings.rag_docs_dir).resolve()

    providers = set(args.providers)
    if "all" in providers:
        providers = {"wikipedia", "worldbank"}

    written = 0
    if "wikipedia" in providers:
        written += _fetch_wikipedia_corpus(manifest, out_dir)
    if "worldbank" in providers:
        written += _fetch_world_bank_corpus(manifest, out_dir)

    print(f"Fetched {written} open-corpus document(s) into {out_dir}")


if __name__ == "__main__":
    main()
