import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", ""))
    max_claims: int = field(default_factory=lambda: int(os.getenv("MAX_CLAIMS", "5")))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    retrieval_mode: str = field(default_factory=lambda: os.getenv("RETRIEVAL_MODE", "web").strip().lower())
    rag_backend: str = field(default_factory=lambda: os.getenv("RAG_BACKEND", "qdrant").strip().lower())
    rag_collection: str = field(default_factory=lambda: os.getenv("RAG_COLLECTION", "factcheck_corpus"))
    rag_top_k: int = field(default_factory=lambda: int(os.getenv("RAG_TOP_K", "5")))
    rag_score_threshold: float = field(default_factory=lambda: float(os.getenv("RAG_SCORE_THRESHOLD", "0")))
    rerank_mode: str = field(default_factory=lambda: os.getenv("RERANK_MODE", "off").strip().lower())
    rerank_max_candidates: int = field(default_factory=lambda: int(os.getenv("RERANK_MAX_CANDIDATES", "8")))
    rerank_diversity_weight: float = field(default_factory=lambda: float(os.getenv("RERANK_DIVERSITY_WEIGHT", "6.0")))
    retrieval_diagnostics_enabled: bool = field(
        default_factory=lambda: os.getenv("RETRIEVAL_DIAGNOSTICS_ENABLED", "1") == "1"
    )
    rag_index_dir: str = field(
        default_factory=lambda: os.getenv(
            "RAG_INDEX_DIR",
            os.path.join(os.getenv("DATA_DIR", "./data"), "rag_index"),
        )
    )
    rag_docs_dir: str = field(
        default_factory=lambda: os.getenv(
            "RAG_DOCS_DIR",
            os.path.join(os.getenv("DATA_DIR", "./data"), "rag_corpus"),
        )
    )
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", ""))
    embedding_base_url: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", os.getenv("LLM_BASE_URL", ""))
    )
    embedding_api_key: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_API_KEY", os.getenv("LLM_API_KEY", ""))
    )

    search_budget: int = field(default_factory=lambda: int(os.getenv("SEARCH_BUDGET", "10")))
    max_rounds_per_claim: int = field(default_factory=lambda: int(os.getenv("MAX_ROUNDS_PER_CLAIM", "2")))
    search_cache_enabled: bool = field(default_factory=lambda: os.getenv("SEARCH_CACHE_ENABLED", "1") == "1")
    search_cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "86400")))

    enable_fetch: bool = field(default_factory=lambda: os.getenv("ENABLE_FETCH", "0") == "1")
    fetch_budget: int = field(default_factory=lambda: int(os.getenv("FETCH_BUDGET", "4")))
    fetch_cache_enabled: bool = field(default_factory=lambda: os.getenv("FETCH_CACHE_ENABLED", "1") == "1")
    fetch_cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("FETCH_CACHE_TTL_SECONDS", "86400")))
    fetch_max_bytes: int = field(default_factory=lambda: int(os.getenv("FETCH_MAX_BYTES", "4000000")))
    fetch_min_text_chars: int = field(default_factory=lambda: int(os.getenv("FETCH_MIN_TEXT_CHARS", "80")))
    fetch_min_text_ratio: float = field(default_factory=lambda: float(os.getenv("FETCH_MIN_TEXT_RATIO", "0.45")))

    data_dir: str = field(default_factory=lambda: os.getenv("DATA_DIR", "./data"))


def get_settings() -> Settings:
    return Settings()
