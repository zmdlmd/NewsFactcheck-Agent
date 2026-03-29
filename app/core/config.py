import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", ""))
    max_claims: int = field(default_factory=lambda: int(os.getenv("MAX_CLAIMS", "5")))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))

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
