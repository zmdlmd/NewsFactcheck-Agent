# RAG Phase 5 Summary

## Goal

Phase 5 focused on making the RAG retrieval layer more observable and more flexible.

Phase 4 introduced taxonomy-aware retrieval and stronger hybrid ranking.
Phase 5 adds:

- multi-valued `rag_filters`
- retrieval diagnostics
- optional diversity reranking

## What Changed

### 1. Multi-Valued Taxonomy Filters

Updated `app/tools/taxonomy.py` so `rag_filters` no longer have to be single-value key-value pairs.

The normalization layer now supports:

- single strings
- comma-separated strings
- short lists

Examples:

- `{"lang": "en,zh"}`
- `{"category": ["report", "data"]}`
- `{"source_policy": ["official", "institutional"]}`

The output is normalized into canonical list-based filters.

### 2. SearchPlan Now Supports Multi-Valued Filters

Updated `app/agent/models.py` so `SearchPlan.rag_filters` now accepts:

- `str`
- `List[str]`

Planner prompts were also updated in `app/agent/prompts/planning.py` so the model is explicitly allowed to emit short lists when more than one stable corpus slice is relevant.

### 3. Planner Post-Processing Preserves Multi-Valued Canonical Filters

Updated `app/agent/node_handlers/planning.py` so planner output is now finalized into normalized list-based taxonomy filters.

The same post-processing step still adds safe defaults when appropriate, but now those defaults are emitted in the same list-based format.

Examples:

- `lang -> ["en"]`
- `category -> ["report"]`

### 4. Qdrant Query Filters Now Support OR Semantics Per Key

Updated `app/tools/rag.py` so query filters now map to:

- `MatchValue` for single values
- `MatchAny` for multiple values

This means Phase 5 supports the intended semantics:

- OR within one metadata field
- AND across different metadata fields

For example:

- `lang in {"en", "zh"}`
- AND `category in {"report"}`

### 5. Retrieval Diagnostics

Updated `app/tools/retrieval.py` to add:

- `retrieve_sources_detailed(...)`
- `format_retrieval_diagnostics(...)`

The original `retrieve_sources(...)` function still exists for compatibility and simply returns the source list.

The detailed retrieval entry point now returns:

- final sources
- retrieval diagnostics

Diagnostics include:

- retrieval mode
- normalized `rag_filters`
- source counts for `rag`, `web`, `merged`, and `returned`
- rerank mode
- whether reranking was actually used
- top result score breakdowns when diagnostics are enabled

### 6. Research Nodes Now Log Retrieval Diagnostics

Updated `app/agent/node_handlers/research.py` so `node_pro_search` and `node_con_search` still behave the same functionally, but now also log retrieval diagnostics when enabled.

This makes it easier to debug:

- why a search returned few results
- what filter slice was used
- whether reranking changed the final order

### 7. Optional Diversity Reranker

Updated `app/tools/retrieval.py` so the retrieval layer now supports an optional diversity rerank mode.

Current behavior:

- `RERANK_MODE=off`
  - keep score-sorted results
- `RERANK_MODE=diversity`
  - apply a lightweight greedy reranker over the top candidate pool

The diversity reranker penalizes repeated evidence from the same:

- source name
- domain
- category
- source policy
- source type

This helps reduce result lists that are semantically similar but provenance-redundant.

### 8. New Runtime Configuration

Added Phase 5 settings in:

- `app/core/config.py`
- `.env.example`

New variables:

- `RERANK_MODE`
- `RERANK_MAX_CANDIDATES`
- `RERANK_DIVERSITY_WEIGHT`
- `RETRIEVAL_DIAGNOSTICS_ENABLED`

## Validation

Phase 5 was validated with:

- `C:\Users\57211\.conda\envs\llava_env\python.exe -m compileall app tests scripts`
- `C:\Users\57211\.conda\envs\llava_env\python.exe -m unittest discover -s tests -v`

New or updated tests cover:

- planner normalization to list-based `rag_filters`
- taxonomy normalization for list-based filters
- Qdrant multi-value filter behavior
- retrieval diagnostics output
- diversity reranking behavior
- research-node diagnostics logging
- Phase 5 config loading

Current suite status after Phase 5:

- `51` tests passing

## Result

After Phase 5, the RAG layer is stronger in three ways:

- it can express broader but still structured corpus slices
- it is easier to inspect and debug
- it can prefer a more diverse final evidence set when requested

The project now has a much better foundation for research-style retrieval experiments because retrieval behavior is no longer a black box.

## Remaining Gap

Phase 5 still uses deterministic heuristics for reranking and diagnostics.

The next logical phase would be:

- add score calibration or cross-encoder reranking
- surface diagnostics through API responses instead of logs only
- persist retrieval traces for offline evaluation
- support weighted or negative metadata filters
