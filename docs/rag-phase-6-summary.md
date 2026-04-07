# RAG Phase 6 Summary

## Goal

Phase 6 focused on turning retrieval from an internal-only subsystem into a debuggable API-facing capability.

Phase 5 added:

- multi-valued `rag_filters`
- retrieval diagnostics
- optional diversity reranking

Phase 6 extends that in two directions:

- surface retrieval diagnostics through the service API and persisted run records
- add an optional LLM-based reranker for final evidence ordering

## What Changed

### 1. Retrieval Diagnostics Are Now Part of Agent State

Updated `app/agent/state.py` and `app/agent/state_factory.py` so retrieval diagnostics are now accumulated as first-class state instead of existing only in log strings.

New state field:

- `retrieval_diagnostics`

This makes diagnostics available to later layers without scraping logs.

### 2. Search Nodes Now Emit Structured Diagnostics

Updated `app/agent/node_handlers/research.py`.

`node_pro_search` and `node_con_search` now call `retrieve_sources_detailed(...)` and append a structured diagnostics entry for each search step.

Each diagnostics record now includes:

- `side`
- `claim_id`
- `query`
- retrieval mode
- normalized `rag_filters`
- rerank mode
- counts for `rag`, `web`, `merged`, and `returned`
- optional `top_results`

The original lightweight log lines remain, so the operator still gets readable console logs.

### 3. Diagnostics Are Now Returned by the API

Updated:

- `app/api.py`
- `app/services/factcheck_runner.py`
- `app/routes.py`

Both synchronous and async status responses now expose:

- `retrieval_diagnostics`

This means diagnostics are no longer trapped inside the LangGraph execution state or server logs.

They are now available through:

- `POST /check/sync`
- `GET /runs/{run_id}`
- `GET /sessions/{session_id}/latest`

### 4. Diagnostics Are Persisted in Session Records

Updated `app/services/factcheck_runner.py`.

Completed and failed runs now persist `retrieval_diagnostics` inside the saved response payload.

This matters for offline analysis because retrieval traces survive process exit and can be inspected after the run completes or fails.

### 5. Optional LLM Reranker

Updated `app/tools/retrieval.py` to add a second rerank mode:

- `RERANK_MODE=llm`

Current rerank options are now:

- `off`
- `diversity`
- `llm`

The LLM reranker works as a shortlist reorderer:

1. retrieval still builds a candidate pool with the existing hybrid scoring logic
2. the top candidate pool is passed to the model with stable candidate IDs
3. the model returns `ordered_ids`
4. retrieval reorders the pool accordingly

The reranker is intentionally narrow in scope:

- it only reorders shortlisted evidence
- it does not replace the main retrieval stack
- it falls back cleanly if the rerank call fails

### 6. Stable Candidate IDs for LLM Reranking

While implementing the LLM reranker, candidate IDs were normalized so they stay tied to the original candidate position rather than the temporary pre-rerank sort order.

This fixes an observability problem:

- diagnostics and tests can now reason about candidate identity more reliably
- the LLM sees a stable candidate list for the current retrieval step

### 7. Failure Handling Remains Safe

The LLM reranker is wrapped so that rerank failures do not break retrieval.

If the rerank call fails:

- retrieval falls back to the default scored order
- diagnostics record `llm_rerank_error`

This keeps Phase 6 safe for production-style experimentation.

## Validation

Phase 6 was validated with:

- `C:\Users\57211\.conda\envs\llava_env\python.exe -m compileall app tests scripts`
- `C:\Users\57211\.conda\envs\llava_env\python.exe -m unittest discover -s tests -v`

New or updated tests cover:

- retrieval diagnostics initialization in state
- runner propagation and persistence of `retrieval_diagnostics`
- API responses returning `retrieval_diagnostics`
- research-node emission of structured diagnostics
- LLM rerank behavior in hybrid retrieval

Current suite status after Phase 6:

- `52` tests passing

## Result

After Phase 6, the retrieval layer is stronger in two practical ways:

- it is externally inspectable through the API and saved run records
- it supports a model-based reranking stage without destabilizing the existing heuristic retrieval pipeline

This is a meaningful shift in project maturity.

The system is no longer just retrieving evidence; it can now explain what it retrieved and why that evidence order changed.

## Remaining Gap

Phase 6 still keeps reranking lightweight and generic.

The next logical phase would be:

- expose richer diagnostics in the UI
- persist retrieval traces in a more evaluation-friendly format
- add optional cross-encoder reranking beside the LLM reranker
- add claim-type-specific rerank prompts or calibration
