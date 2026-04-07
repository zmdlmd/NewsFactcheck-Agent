# RAG Phase 2 Summary

## Goal

Phase 2 focused on making planning RAG-aware instead of only retrieval-aware.

Phase 1 allowed the system to execute RAG retrieval.
Phase 2 allows the planner to shape that retrieval through structured `rag_filters`.

## What Changed

### 1. SearchPlan Schema

Extended `SearchPlan` in `app/agent/models.py`:

- added `rag_filters: Dict[str, str]`

This lets the planner express lightweight metadata constraints for internal corpus retrieval.

### 2. Planning Prompt Upgrade

Rewrote `app/agent/prompts/planning.py` into a clean ASCII version and added explicit guidance for:

- when to use `rag_filters`
- when to leave `rag_filters` empty
- what kinds of metadata keys are appropriate

This also removed historical encoding-noise from the planning prompt file.

### 3. Planner Normalization

Updated `app/agent/node_handlers/planning.py` to:

- normalize `rag_filters`
- strip empty keys and values
- cap filter count

This prevents malformed planner output from leaking into retrieval.

### 4. Retrieval Propagation

Updated `app/agent/node_handlers/research.py` so `node_pro_search` and `node_con_search` both pass:

- `query`
- `include_domains`
- `exclude_domains`
- `rag_filters`

through to `retrieve_sources(...)`.

This completed the end-to-end path:

`planner -> search_plan -> retrieval -> rag search`

### 5. Qdrant Filter Mapping

Updated `app/tools/rag.py` so filter keys can target:

- top-level payload fields such as `doc_id`, `chunk_id`, `title`, `source_name`
- nested metadata via automatic `metadata.` prefixing

This made planner-generated metadata filtering practically usable.

## Validation

Phase 2 added tests for:

- planner normalization of `rag_filters`
- default empty `rag_filters`
- propagation of `rag_filters` from planner to retrieval

Validation run:

- `python -m compileall app tests scripts`
- `python -m unittest discover -s tests -v`

Current suite status after Phase 2:

- `40` tests passing

## Result

After Phase 2, the system no longer treats RAG as just a passive fallback source.
The planner can now influence internal retrieval scope through structured metadata filters.

This is the first step toward:

- corpus-aware planning
- claim-type-specific internal retrieval
- domain- or language-specific knowledge routing

## Remaining Gap

Phase 2 still uses generic planner reasoning.
The next logical phase would be:

- teach supervisor/planner to generate better `rag_filters` based on claim type, corpus type, and source policy
- optionally add retrieval-time reranking across web and RAG evidence
