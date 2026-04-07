from __future__ import annotations

import hashlib
import os
from typing import Any, Iterable
from urllib.parse import quote

from app.core.config import Settings, get_settings
from app.tools.taxonomy import normalize_rag_filters, normalize_taxonomy_metadata


def make_rag_url(doc_id: str, chunk_id: str) -> str:
    safe_doc_id = quote((doc_id or "doc").strip(), safe="")
    safe_chunk_id = quote((chunk_id or "chunk-0").strip(), safe="")
    return f"rag://{safe_doc_id}/{safe_chunk_id}"


def _rag_storage_path(settings: Settings) -> str:
    path = (settings.rag_index_dir or "").strip() or os.path.join(settings.data_dir, "rag_index")
    if path != ":memory:":
        os.makedirs(path, exist_ok=True)
    return path


def _build_embeddings(settings: Settings):
    if not (settings.embedding_model or "").strip():
        raise RuntimeError("EMBEDDING_MODEL is required when RETRIEVAL_MODE uses RAG")

    from langchain_openai import OpenAIEmbeddings

    kwargs: dict[str, Any] = {
        "model": settings.embedding_model,
        # DashScope's OpenAI-compatible embeddings endpoint expects raw strings.
        # Disable LangChain's token-length splitting path to avoid sending token arrays.
        "check_embedding_ctx_length": False,
        # DashScope rejects embedding batches larger than 10 inputs.
        "chunk_size": 10,
    }
    if settings.embedding_base_url:
        kwargs["openai_api_base"] = settings.embedding_base_url
    if settings.embedding_api_key:
        kwargs["openai_api_key"] = settings.embedding_api_key
    return OpenAIEmbeddings(**kwargs)


def _build_qdrant_client(settings: Settings):
    from qdrant_client import QdrantClient

    return QdrantClient(path=_rag_storage_path(settings))


def _build_query_filter(filters: dict[str, Any] | None):
    normalized_filters = normalize_rag_filters(filters)
    if not normalized_filters:
        return None

    from qdrant_client.http import models as qmodels

    conditions = []
    top_level_keys = {"doc_id", "chunk_id", "title", "source_name", "origin_url"}
    for key, values in normalized_filters.items():
        if not values:
            continue
        field_key = key if key in top_level_keys or key.startswith("metadata.") else f"metadata.{key}"
        match = (
            qmodels.MatchAny(any=values)
            if len(values) > 1
            else qmodels.MatchValue(value=values[0])
        )
        conditions.append(
            qmodels.FieldCondition(
                key=field_key,
                match=match,
            )
        )
    if not conditions:
        return None
    return qmodels.Filter(must=conditions)


def _ensure_collection(client, settings: Settings, vector_size: int, *, recreate: bool = False) -> None:
    from qdrant_client.http import models as qmodels

    exists = client.collection_exists(settings.rag_collection)
    if recreate and exists:
        client.delete_collection(settings.rag_collection)
        exists = False
    if exists:
        return

    client.create_collection(
        collection_name=settings.rag_collection,
        vectors_config=qmodels.VectorParams(
            size=vector_size,
            distance=qmodels.Distance.COSINE,
        ),
    )


def _snippet_from_text(text: str, max_chars: int = 320) -> str:
    compact = " ".join((text or "").strip().split())
    return compact[:max_chars]


def _point_id(doc_id: str, chunk_id: str) -> int:
    digest = hashlib.sha1(f"{doc_id}:{chunk_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _normalize_rag_source(payload: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    metadata = normalize_taxonomy_metadata(
        payload.get("metadata") or {},
        title=str(payload.get("title") or ""),
        source_name=str(payload.get("source_name") or ""),
        path=str((payload.get("metadata") or {}).get("path") or ""),
    )
    doc_id = str(payload.get("doc_id") or metadata.get("doc_id") or "doc")
    chunk_id = str(payload.get("chunk_id") or metadata.get("chunk_id") or "chunk-0")
    page_text = (payload.get("page_text") or payload.get("text") or "").strip() or None
    title = (payload.get("title") or metadata.get("title") or doc_id).strip()
    source_name = (payload.get("source_name") or metadata.get("source_name") or "RAG").strip()

    origin_url = (payload.get("origin_url") or metadata.get("origin_url") or payload.get("url") or "").strip()
    if origin_url and "origin_url" not in metadata:
        metadata["origin_url"] = origin_url

    return {
        "title": title,
        "url": make_rag_url(doc_id, chunk_id),
        "snippet": (payload.get("snippet") or _snippet_from_text(page_text or "")).strip(),
        "page_text": page_text,
        "source_type": "rag",
        "source_name": source_name,
        "doc_id": doc_id,
        "chunk_id": chunk_id,
        "score": score if score is not None else payload.get("score"),
        "metadata": metadata,
    }


def rag_search(
    query: str,
    *,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    query = (query or "").strip()
    if not query:
        return []

    if settings.rag_backend != "qdrant":
        raise NotImplementedError(f"Unsupported RAG backend: {settings.rag_backend}")

    client = _build_qdrant_client(settings)
    if not client.collection_exists(settings.rag_collection):
        return []

    embeddings = _build_embeddings(settings)
    query_vector = embeddings.embed_query(query)
    response = client.query_points(
        collection_name=settings.rag_collection,
        query=query_vector,
        query_filter=_build_query_filter(filters),
        limit=top_k or settings.rag_top_k,
        with_payload=True,
        score_threshold=settings.rag_score_threshold if settings.rag_score_threshold > 0 else None,
    )

    out: list[dict[str, Any]] = []
    for point in response.points:
        payload = dict(point.payload or {})
        out.append(_normalize_rag_source(payload, score=float(point.score)))
    return out


def index_documents(
    documents: Iterable[dict[str, Any]],
    *,
    recreate: bool = False,
) -> int:
    settings = get_settings()
    if settings.rag_backend != "qdrant":
        raise NotImplementedError(f"Unsupported RAG backend: {settings.rag_backend}")

    docs = [dict(doc) for doc in documents if (doc.get("page_text") or doc.get("text") or "").strip()]
    if not docs:
        return 0

    embeddings = _build_embeddings(settings)
    texts = [((doc.get("page_text") or doc.get("text") or "").strip()) for doc in docs]
    vectors = embeddings.embed_documents(texts)
    if not vectors:
        return 0

    client = _build_qdrant_client(settings)
    _ensure_collection(client, settings, len(vectors[0]), recreate=recreate)

    from qdrant_client.http import models as qmodels

    points = []
    for doc, text, vector in zip(docs, texts, vectors):
        metadata = normalize_taxonomy_metadata(
            doc.get("metadata") or {},
            title=str(doc.get("title") or ""),
            source_name=str(doc.get("source_name") or ""),
            path=str((doc.get("metadata") or {}).get("path") or ""),
        )
        doc_id = str(doc.get("doc_id") or metadata.get("doc_id") or metadata.get("path") or "doc")
        chunk_id = str(doc.get("chunk_id") or metadata.get("chunk_id") or "chunk-0")
        title = (doc.get("title") or metadata.get("title") or doc_id).strip()
        source_name = (doc.get("source_name") or metadata.get("source_name") or "RAG").strip()
        origin_url = (doc.get("origin_url") or metadata.get("origin_url") or doc.get("url") or "").strip()
        if origin_url and "origin_url" not in metadata:
            metadata["origin_url"] = origin_url

        payload = {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "title": title,
            "source_name": source_name,
            "snippet": (doc.get("snippet") or _snippet_from_text(text)).strip(),
            "page_text": text,
            "metadata": metadata,
        }
        if origin_url:
            payload["origin_url"] = origin_url

        points.append(
            qmodels.PointStruct(
                id=_point_id(doc_id, chunk_id),
                vector=vector,
                payload=payload,
            )
        )

    client.upsert(settings.rag_collection, points, wait=True)
    return len(points)
