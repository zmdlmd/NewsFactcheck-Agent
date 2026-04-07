from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import get_settings
from app.tools.claim_profile import detect_text_language
from app.tools.rag import index_documents
from app.tools.taxonomy import normalize_taxonomy_metadata


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def _iter_corpus_files(root: Path) -> list[Path]:
    suffixes = {".txt", ".md"}
    return [path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in suffixes]


def _documents_from_file(path: Path, root: Path, chunk_size: int, chunk_overlap: int) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []

    relative_path = path.relative_to(root).as_posix()
    doc_id = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]
    title = path.stem
    language = detect_text_language(text)
    base_metadata = normalize_taxonomy_metadata(
        {
            "path": relative_path,
            "title": title,
            "source_name": "local-corpus",
            "lang": language,
        },
        title=title,
        source_name="local-corpus",
        path=relative_path,
    )
    docs = []
    for index, chunk in enumerate(_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)):
        docs.append(
            {
                "doc_id": doc_id,
                "chunk_id": f"chunk-{index}",
                "title": title,
                "page_text": chunk,
                "source_name": "local-corpus",
                "metadata": dict(base_metadata),
            }
        )
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local RAG index from text/markdown files")
    parser.add_argument("--docs-dir", default=None, help="Override RAG_DOCS_DIR")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    settings = get_settings()

    docs_root = Path(args.docs_dir or settings.rag_docs_dir).resolve()
    if not docs_root.exists():
        raise SystemExit(f"Corpus directory not found: {docs_root}")

    all_documents = []
    for path in _iter_corpus_files(docs_root):
        all_documents.extend(
            _documents_from_file(
                path,
                docs_root,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
        )

    if not all_documents:
        raise SystemExit(f"No .txt or .md files found in {docs_root}")

    indexed = index_documents(all_documents, recreate=args.recreate)
    print(f"Indexed {indexed} chunk(s) into collection `{settings.rag_collection}` from {docs_root}")


if __name__ == "__main__":
    main()
