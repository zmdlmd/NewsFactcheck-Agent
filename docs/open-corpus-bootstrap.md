# Open Corpus Bootstrap

This document describes the first reproducible public-data bootstrap for the local RAG knowledge base.

## Goal

Build a small but credible starter corpus from official public sources that fit the current project shape:

- text-like content
- stable public APIs
- easy conversion into `.md`
- suitable for fact-check retrieval

## Selected Sources

### 1. Wikipedia via MediaWiki REST API

The bootstrap script fetches Wikipedia article content through the official MediaWiki REST endpoint:

- `GET /page/{title}/with_html`

This endpoint returns page metadata, license information, latest revision metadata, and HTML content.

Reference:

- https://www.mediawiki.org/wiki/API:REST_API/Reference

### 2. World Bank Indicators API V2

The bootstrap script fetches indicator metadata and recent values through the official World Bank Indicators API.

Reference:

- https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation

The World Bank documentation states that:

- V2 is the supported API version
- the API can be called directly through HTTP
- no API key is required

For licensing, the World Bank Data Catalog states that open datasets are generally distributed under CC BY 4.0.

Reference:

- https://datacatalog1.worldbank.org/public-licenses

## What Gets Downloaded

The starter manifest lives at:

- `scripts/open_corpus_manifest.json`

It currently includes:

- Wikipedia topic pages such as `Earth`, `Solar System`, `United Nations`, `Climate change`
- World Bank indicators such as:
  - `SP.POP.TOTL`
  - `NY.GDP.MKTP.CD`
  - `SP.DYN.LE00.IN`
  - `FP.CPI.TOTL.ZG`
  - `EN.ATM.CO2E.PC`

## Output Layout

Generated files are written under `RAG_DOCS_DIR`, by default:

- `data/rag_corpus/open/reference/wikipedia/...`
- `data/rag_corpus/open/official/data/world-bank/...`

This path layout is intentional because the current taxonomy inference already uses path segments such as:

- `reference`
- `official`
- `data`

to improve retrieval metadata.

## Commands

One-click bootstrap on Windows:

```powershell
.\bootstrap_open_rag.ps1
```

Or double-click:

```text
bootstrap_open_rag.bat
```

The script will:

- fetch the configured public corpus sources
- rebuild the local vector index
- write logs to `data/logs/open-rag-bootstrap.out.log` and `data/logs/open-rag-bootstrap.err.log`

Optional examples:

```powershell
.\bootstrap_open_rag.ps1 -Providers wikipedia
.\bootstrap_open_rag.ps1 -Providers worldbank
.\bootstrap_open_rag.ps1 -SkipFetch
```

Fetch the starter corpus:

```powershell
$env:PYTHONPATH='.'
python scripts\fetch_open_corpus.py
```

Rebuild the local vector index:

```powershell
$env:PYTHONPATH='.'
python scripts\build_rag_index.py --recreate
```

## Notes

- The generated corpus is local runtime data and should not be committed.
- The project currently ingests `.md` and `.txt` files only.
- This bootstrap is intended as a first knowledge base, not a complete production corpus.

## Next Extension

After this starter corpus, the next useful additions would be:

- more official statistical sources
- fact-check article archives
- domain-specific corpora such as climate, public health, or macroeconomics
