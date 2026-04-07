# RAG Phase 1 Summary

## Goal

Phase 1 focused on introducing RAG into the existing fact-check pipeline with minimal intrusion:

- keep the LangGraph main flow unchanged
- add a new RAG retrieval source
- support `web`, `rag`, and `hybrid` retrieval modes
- make RAG hits compatible with existing judge/report stages

## What Changed

### 1. Config

Added RAG-related settings in `app/core/config.py`:

- `RETRIEVAL_MODE`
- `RAG_BACKEND`
- `RAG_COLLECTION`
- `RAG_TOP_K`
- `RAG_SCORE_THRESHOLD`
- `RAG_INDEX_DIR`
- `RAG_DOCS_DIR`
- `EMBEDDING_MODEL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`

This made retrieval mode a runtime configuration instead of a code fork.

### 2. Source Schema

Extended `SourceItem` in `app/agent/models.py` so the system can represent both web and RAG evidence:

- `source_type`
- `source_name`
- `doc_id`
- `chunk_id`
- `score`
- `metadata`

This preserved compatibility with the current pipeline while making source provenance richer.

### 3. RAG Tool Layer

Added `app/tools/rag.py` with:

- `rag_search(...)`
- `index_documents(...)`
- Qdrant local persistence support
- OpenAI-compatible embedding support

RAG hits are normalized into the same evidence shape used elsewhere in the project.

### 4. Unified Retrieval Layer

Added `app/tools/retrieval.py` with:

- `search_web(...)`
- `search_rag(...)`
- `retrieve_sources(...)`

This is now the single retrieval entry point for the research nodes.

### 5. Research Node Integration

Updated `app/agent/node_handlers/research.py` to:

- use `retrieve_sources(...)` instead of directly calling Tavily
- merge web and RAG evidence using the same source list
- skip `fetch_page_text(...)` for `source_type="rag"` sources

This was the key step that let RAG enter the existing graph without rewriting the graph itself.

### 6. Offline Index Build Script

Added `scripts/build_rag_index.py` to:

- scan a local corpus directory
- chunk text/markdown files
- embed chunks
- write them into the Qdrant collection

This separates ingestion from online fact-check execution.

### 7. Environment and Dependency Updates

Updated:

- `.env.example`
- `requirements.txt`

Added `qdrant-client` as the first vector DB dependency.

## Validation

Phase 1 was verified with:

- `python -m compileall app tests scripts`
- `python -m unittest discover -s tests -v`

Key new tests covered:

- RAG indexing and retrieval round-trip
- retrieval mode switching
- hybrid merge behavior
- RAG-aware fetch skipping

## Result

After Phase 1, the project can:

- run in pure web mode
- run in pure RAG mode
- run in hybrid mode
- use local vector retrieval without changing the LangGraph structure

The main limitation left after Phase 1 was that planners still generated only web-oriented search plans. RAG existed as a retrieval capability, but not yet as a planner-aware retrieval target.
