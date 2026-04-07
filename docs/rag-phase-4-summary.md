# RAG Phase 4 Summary

## Goal

Phase 4 focused on replacing ad hoc internal-corpus filtering with a stable taxonomy layer and strengthening hybrid reranking beyond raw retrieval scores.

Phase 3 made retrieval claim-aware.
Phase 4 makes metadata and reranking policy-aware.

## What Changed

### 1. Added a Shared Taxonomy Layer

Added `app/tools/taxonomy.py` as the canonical metadata and filter normalization layer.

It now standardizes:

- filter keys such as `lang`, `category`, `topic`, `institution`, `region`, `source_policy`
- common aliases such as `language -> lang`, `type -> category`, `policy -> source_policy`
- metadata values such as:
  - `press release -> announcement`
  - `annual report -> report`
  - `statistics -> data`
  - `gov -> official`

This removed the previous ambiguity where planners or ingestion code could emit many near-duplicate key/value variants.

### 2. Planner Output Now Uses Canonical Taxonomy

Updated:

- `app/agent/prompts/planning.py`
- `app/agent/node_handlers/planning.py`

The planner prompt now explicitly instructs the model to use canonical taxonomy fields and values.

Planner node post-processing now:

- normalizes LLM-generated `rag_filters`
- maps alias keys/values into canonical taxonomy
- adds stable defaults in `rag` and `hybrid` modes when safe

Current defaults are conservative:

- add `lang` when the claim language is clearly `en` or `zh`
- add `category=report` for clearly numeric non-temporal claims
- add `category=announcement` for clearly temporal non-numeric claims

This keeps planner output structured without overconstraining mixed claims.

### 3. RAG Ingestion Now Writes Taxonomy Metadata

Updated `scripts/build_rag_index.py` to normalize metadata before indexing.

Indexed chunks can now carry canonical metadata such as:

- `lang`
- `category`
- `topic`
- `region`
- `source_policy`

The ingestion path also infers missing taxonomy fields from local corpus paths and filenames when possible.

This means corpus metadata is now more queryable and less dependent on perfectly hand-authored annotations.

### 4. RAG Search Filters Now Normalize Before Querying

Updated `app/tools/rag.py` so query-time filters are normalized before building the Qdrant filter object.

This means searches such as:

- `language=English`
- `type=press release`
- `policy=gov`

can still hit the correct corpus slices after being normalized to:

- `lang=en`
- `category=announcement`
- `source_policy=official`

This makes planner output and manual retrieval much more robust.

### 5. Hybrid Reranking Is Now Stronger

Updated `app/tools/retrieval.py` so hybrid reranking now uses more than:

- raw RAG similarity
- raw web source quality

It now combines:

- retrieval score
- claim-aware evidence-style bonuses
- lexical overlap between claim/query and source text
- taxonomy quality signals
- source policy quality

Examples of the new scoring behavior:

- official or institutional sources receive stronger support than community sources
- evidence with better lexical coverage of the claim gets promoted
- category-aligned sources keep a quality advantage even when semantic scores are close

This is the first phase where hybrid retrieval has a clear policy layer for ranking evidence, not just a source-merging layer.

## Validation

Phase 4 was validated with:

- `C:\Users\57211\.conda\envs\llava_env\python.exe -m compileall app tests scripts`
- `C:\Users\57211\.conda\envs\llava_env\python.exe -m unittest discover -s tests -v`

New or updated tests cover:

- taxonomy alias normalization
- taxonomy metadata inference from corpus paths
- planner taxonomy normalization
- planner default taxonomy filters in hybrid mode
- RAG filter normalization at query time
- hybrid reranking using taxonomy and lexical overlap

Current suite status after Phase 4:

- `48` tests passing

## Result

After Phase 4, the project has moved from:

- claim-aware retrieval with flexible metadata

to:

- taxonomy-aware retrieval with normalized corpus metadata and a stronger hybrid reranker

The RAG stack is now more stable in three ways:

- planner output is more structured
- corpus metadata is more consistent
- evidence ranking is more defensible

## Remaining Gap

Phase 4 still uses deterministic heuristics for taxonomy inference and reranking.

The next logical phase would be:

- add corpus-specific metadata extraction during ingestion
- support multi-valued filters instead of single key-value filters
- introduce an optional cross-encoder or LLM reranker
- expose taxonomy-aware retrieval diagnostics in logs or API responses
