# RAG Phase 3 Summary

## Goal

Phase 3 focused on making retrieval quality claim-aware instead of only mode-aware.

Phase 1 added RAG retrieval.
Phase 2 let the planner emit structured `rag_filters`.
Phase 3 teaches the planner and hybrid ranking layer to reason about:

- claim type
- claim time sensitivity
- claim language
- evidence style fit

## What Changed

### 1. Shared Claim Profile Helper

Added `app/tools/claim_profile.py` with:

- `detect_text_language(...)`
- `build_claim_profile(...)`
- `summarize_claim_profile(...)`

This created one reusable place for extracting lightweight claim features such as:

- `numeric`
- `temporal`
- `years`
- `language`

The same profile logic is now reused across planning, retrieval, and corpus ingestion.

### 2. Planner Prompt Now Includes Retrieval Context

Updated `app/agent/prompts/planning.py` so the planner prompt now includes:

- `Retrieval mode`
- `Claim profile`

The prompt also gives explicit guidance that:

- numeric claims often align with report/data/statistics evidence
- temporal claims often align with news/press/update/announcement evidence
- language metadata can be useful when generating `rag_filters`

This makes the planner more likely to produce retrieval plans that match the evidence type actually needed by the claim.

### 3. Planner Nodes Now Generate Claim-Aware Search Plans

Updated `app/agent/node_handlers/planning.py` so both:

- `node_pro_planner`
- `node_con_planner`

now compute a claim profile summary and pass it into `planner_user_prompt(...)`.

This means the planner is no longer operating only on raw claim text.
It now gets a compact view of the claim's structure and can produce better queries and better `rag_filters`.

### 4. Retrieval Layer Now Uses Claim-Aware Hybrid Reranking

Updated `app/tools/retrieval.py` so hybrid retrieval ranking now considers:

- semantic RAG score
- web source quality score
- numeric-claim evidence hints
- temporal-claim evidence hints
- year alignment
- PDF/report preference where appropriate
- language match between claim and source

Examples of the new behavior:

- numeric claims boost report/data/statistics-like evidence
- temporal claims boost news/update/announcement-like evidence
- purely temporal claims no longer over-prefer PDF-style evidence
- language mismatches can be slightly penalized

This is the first phase where `hybrid` retrieval is doing real claim-aware evidence selection instead of simple source merging.

### 5. Research Nodes Propagate Claim Text Into Retrieval

Updated `app/agent/node_handlers/research.py` so `node_pro_search` and `node_con_search` now pass the active claim text into `retrieve_sources(...)`.

This completed the execution path:

`claim -> claim profile -> planner -> retrieval -> claim-aware rerank`

### 6. RAG Ingestion Now Stores Language Metadata

Updated `scripts/build_rag_index.py` so indexed corpus chunks now carry:

- `metadata.lang`

This supports language-aware filtering and ranking during retrieval.

## Validation

Phase 3 was validated with:

- `python -m compileall app tests scripts`
- `python -m unittest discover -s tests -v`

New or updated tests cover:

- planner prompts including retrieval mode and claim profile
- planner node handling of claim-aware planning inputs
- hybrid retrieval preferring report-like RAG evidence for numeric claims
- hybrid retrieval preferring news-like evidence for temporal claims
- end-to-end propagation of claim text into retrieval

Current suite status after Phase 3:

- `43` tests passing

## Result

After Phase 3, the project has moved from:

- RAG-capable retrieval

to:

- claim-aware hybrid retrieval

The planner now has better context for generating search plans, and the retrieval layer now does a more defensible job of ranking evidence based on what the claim actually requires.

## Remaining Gap

Phase 3 still uses heuristic claim profiling and heuristic reranking.
The next logical phase would be:

- introduce corpus-specific metadata taxonomies
- add stronger rerankers or cross-encoders
- let the supervisor adapt budgets and tool choice based on claim profile
- add richer `rag_filters` generation for institution, region, topic, and source policy
