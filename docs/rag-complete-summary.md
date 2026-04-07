# RAG Integration Complete Summary

## Overview

This document consolidates the RAG work completed across Phase 1 to Phase 6.

The project started as a web-search-centric fact-checking agent built on:

- FastAPI
- LangGraph
- OpenAI-compatible LLM calls
- Tavily-based web retrieval

The RAG work did not replace that architecture.
Instead, it progressively turned the system into a hybrid evidence engine that can combine:

- web retrieval
- local vector retrieval
- structured metadata filtering
- claim-aware reranking
- API-visible retrieval diagnostics

The design goal across all phases was consistent:

- keep the main LangGraph orchestration stable
- add RAG with minimal disruption
- improve retrieval quality in controlled steps
- preserve testability and observability at each stage

## Architecture Progression

Across the six phases, the retrieval stack evolved like this:

1. Phase 1: add RAG as a new retrieval backend
2. Phase 2: let the planner emit `rag_filters`
3. Phase 3: make planning and ranking claim-aware
4. Phase 4: normalize metadata and filters with a taxonomy layer
5. Phase 5: add multi-value filters, diagnostics, and diversity reranking
6. Phase 6: expose diagnostics through APIs and add an optional LLM reranker

By the end of Phase 6, the effective retrieval pipeline became:

`claim -> planner -> search plan + rag_filters -> web/rag/hybrid retrieval -> rerank -> diagnostics -> judge/report`

## Phase-by-Phase Summary

### Phase 1: Minimal-Intrusion RAG Integration

Phase 1 introduced RAG into the existing fact-check pipeline without changing the LangGraph main flow.

Main changes:

- Added RAG runtime settings in `app/core/config.py`
- Extended `SourceItem` in `app/agent/models.py` so the system can represent both web and RAG evidence
- Added `app/tools/rag.py` for:
  - Qdrant-backed local vector search
  - OpenAI-compatible embeddings
  - document indexing
- Added `app/tools/retrieval.py` as a unified retrieval entry point
- Updated `app/agent/node_handlers/research.py` to use unified retrieval instead of direct Tavily calls
- Added `scripts/build_rag_index.py` for offline corpus ingestion
- Updated `.env.example` and `requirements.txt`

What this achieved:

- `web` mode support
- `rag` mode support
- `hybrid` mode support
- RAG evidence compatibility with the existing judge and report stages
- fetch-step skipping for `source_type="rag"`

Phase 1 established the base capability, but planning was still web-oriented.

### Phase 2: Planner-Aware RAG Retrieval

Phase 2 made RAG planner-aware instead of retrieval-only.

Main changes:

- Extended `SearchPlan` in `app/agent/models.py` with `rag_filters`
- Upgraded `app/agent/prompts/planning.py` so the planner can decide when to emit `rag_filters`
- Added planner-side normalization in `app/agent/node_handlers/planning.py`
- Updated `app/agent/node_handlers/research.py` so planner-generated `rag_filters` propagate into retrieval
- Updated `app/tools/rag.py` so Qdrant filters can target both top-level payload fields and nested metadata

What this achieved:

- planner output can now constrain internal corpus retrieval
- the execution path became:
  - `planner -> search plan -> rag_filters -> retrieval -> rag search`

Validation status after Phase 2:

- `40` tests passing

This phase moved RAG from passive capability to structured retrieval target.

### Phase 3: Claim-Aware Retrieval

Phase 3 made planning and ranking aware of claim type, time sensitivity, year mentions, and language.

Main changes:

- Added `app/tools/claim_profile.py`
- Added reusable helpers:
  - `detect_text_language(...)`
  - `build_claim_profile(...)`
  - `summarize_claim_profile(...)`
- Updated `app/agent/prompts/planning.py` so the planner sees:
  - retrieval mode
  - claim profile
- Updated planner nodes to compute claim profiles and pass them into prompt construction
- Updated `app/tools/retrieval.py` so hybrid ranking considers:
  - semantic RAG score
  - web source quality
  - numeric claim hints
  - temporal claim hints
  - year alignment
  - PDF/report preference where appropriate
  - language match
- Updated `app/agent/node_handlers/research.py` to pass active claim text into retrieval
- Updated `scripts/build_rag_index.py` to store language metadata during ingestion

What this achieved:

- numeric claims prefer report/data/statistics-style evidence
- temporal claims prefer news/update/announcement-style evidence
- language mismatches can be penalized
- hybrid retrieval started making evidence-style decisions instead of simple list merging

Validation status after Phase 3:

- `43` tests passing

This phase marked the move from mode-aware retrieval to claim-aware retrieval.

### Phase 4: Taxonomy-Aware Retrieval

Phase 4 replaced ad hoc metadata handling with a canonical taxonomy layer.

Main changes:

- Added `app/tools/taxonomy.py`
- Standardized canonical filter keys such as:
  - `lang`
  - `category`
  - `topic`
  - `institution`
  - `region`
  - `source_policy`
- Normalized common aliases such as:
  - `language -> lang`
  - `type -> category`
  - `policy -> source_policy`
- Updated planner prompts and planner post-processing to use canonical taxonomy
- Added conservative default filters in `rag` and `hybrid` modes where appropriate
- Updated `scripts/build_rag_index.py` so corpus metadata is normalized before indexing
- Updated `app/tools/rag.py` so retrieval-time filters are normalized before query execution
- Strengthened hybrid ranking in `app/tools/retrieval.py` with:
  - lexical overlap
  - taxonomy quality
  - source policy quality

What this achieved:

- planner output became more structured
- corpus metadata became more queryable
- retrieval filters became robust to aliases and inconsistent input
- hybrid ranking became policy-aware rather than score-only

Validation status after Phase 4:

- `48` tests passing

This phase turned the RAG stack into a taxonomy-aware system instead of a free-form metadata system.

### Phase 5: Multi-Value Filters, Diagnostics, and Diversity Rerank

Phase 5 made the retrieval layer more expressive and more observable.

Main changes:

- Updated `app/tools/taxonomy.py` so `rag_filters` can use:
  - single strings
  - comma-separated strings
  - short lists
- Updated `SearchPlan` so `rag_filters` can carry list values
- Updated planner post-processing so canonical filters remain list-based end to end
- Updated `app/tools/rag.py` to map:
  - single values to `MatchValue`
  - multi-values to `MatchAny`
- Added `retrieve_sources_detailed(...)` and `format_retrieval_diagnostics(...)` in `app/tools/retrieval.py`
- Updated research nodes to log retrieval diagnostics
- Added optional diversity reranking in `app/tools/retrieval.py`
- Added new runtime config:
  - `RERANK_MODE`
  - `RERANK_MAX_CANDIDATES`
  - `RERANK_DIVERSITY_WEIGHT`
  - `RETRIEVAL_DIAGNOSTICS_ENABLED`

What this achieved:

- OR semantics within one taxonomy field
- AND semantics across different fields
- retrievable diagnostics for counts, filters, and rerank behavior
- provenance diversity improvements in the final evidence shortlist

Validation status after Phase 5:

- `51` tests passing

This phase made the retrieval stack inspectable and more suitable for research-style experiments.

### Phase 6: API Diagnostics and LLM Reranking

Phase 6 pushed retrieval diagnostics out of logs and into the service contract, while also adding an optional model-based reranking layer.

Main changes:

- Added `retrieval_diagnostics` to `app/agent/state.py`
- Initialized diagnostics in `app/agent/state_factory.py`
- Updated `app/agent/node_handlers/research.py` so each search step emits structured diagnostics
- Updated:
  - `app/api.py`
  - `app/services/factcheck_runner.py`
  - `app/routes.py`
  so synchronous and asynchronous responses now expose `retrieval_diagnostics`
- Persisted diagnostics into saved run records
- Added `RERANK_MODE=llm` support in `app/tools/retrieval.py`
- Added a lightweight LLM reranker that:
  - receives a shortlisted candidate pool
  - returns `ordered_ids`
  - reorders candidates without replacing the main retrieval pipeline
- Stabilized candidate IDs so rerank diagnostics and tests are reliable
- Added safe fallback behavior so rerank failure does not break retrieval

What this achieved:

- retrieval behavior is now visible through API responses and persisted outputs
- LLM-based shortlist reordering is available without changing the graph
- retrieval traces can be inspected after run completion or failure

Validation status after Phase 6:

- `52` tests passing

This phase made the system significantly more operationally mature.

## End State After Phase 6

After all six phases, the project supports:

- `web`, `rag`, and `hybrid` retrieval modes
- local Qdrant-backed vector retrieval
- OpenAI-compatible embeddings
- planner-generated structured `rag_filters`
- canonical taxonomy normalization
- claim-aware retrieval and reranking
- multi-value metadata filters
- optional diversity reranking
- optional LLM reranking
- retrieval diagnostics through:
  - logs
  - state
  - persisted run records
  - API responses

In practical terms, the retrieval layer is now:

- structured
- claim-aware
- taxonomy-aware
- diagnosable
- extensible

## Main Files Added or Strengthened

The phases collectively centered around these files:

- `app/tools/rag.py`
- `app/tools/retrieval.py`
- `app/tools/taxonomy.py`
- `app/tools/claim_profile.py`
- `scripts/build_rag_index.py`
- `app/agent/node_handlers/planning.py`
- `app/agent/node_handlers/research.py`
- `app/agent/prompts/planning.py`
- `app/agent/models.py`
- `app/core/config.py`
- `app/api.py`
- `app/services/factcheck_runner.py`
- `app/agent/state.py`
- `app/agent/state_factory.py`

## Validation Trajectory

Validation was done incrementally at every phase through:

- `python -m compileall app tests scripts`
- `python -m unittest discover -s tests -v`

Observed test suite progression:

- Phase 2: `40`
- Phase 3: `43`
- Phase 4: `48`
- Phase 5: `51`
- Phase 6: `52`

The suite now covers:

- RAG indexing and search round-trips
- retrieval mode switching
- planner normalization
- taxonomy normalization
- claim-aware ranking
- multi-value metadata filters
- diagnostics propagation
- diversity reranking
- LLM reranking
- runner persistence behavior
- API response contracts

## Current Practical Boundary

The RAG code path is implemented and validated, but it is not automatically active in every environment.

To use RAG in a real run, the environment still needs:

- `RETRIEVAL_MODE=rag` or `RETRIEVAL_MODE=hybrid`
- `EMBEDDING_MODEL`
- a corpus directory under `RAG_DOCS_DIR`
- a built vector index under `RAG_INDEX_DIR`

Without those pieces, the system still runs, but it falls back to pure web retrieval.

## Engineering Takeaways

The most important engineering choices across the six phases were:

- avoid rewriting the graph when the real change belonged in retrieval
- standardize metadata early instead of accepting planner-specific ad hoc filters
- keep retrieval observable, not just accurate
- add reranking as an optional layer, not a hard dependency
- preserve compatibility with existing judge and report stages

Those choices kept the integration incremental and testable.

## Recommended Next Steps

If RAG work continues, the next useful steps are:

1. Add richer diagnostics to the UI instead of only returning them through API payloads.
2. Persist retrieval traces in a more evaluation-friendly format.
3. Add optional cross-encoder reranking beside the current LLM reranker.
4. Improve corpus ingestion with richer metadata extraction.
5. Add a dedicated QA-style endpoint if the goal expands beyond fact-check workflows.

## Reference Documents

This document consolidates the following phase notes:

- `docs/rag-phase-1-summary.md`
- `docs/rag-phase-2-summary.md`
- `docs/rag-phase-3-summary.md`
- `docs/rag-phase-4-summary.md`
- `docs/rag-phase-5-summary.md`
- `docs/rag-phase-6-summary.md`
