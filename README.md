# NDAP Deep Research Agent

Agent-ready tooling for exploring India's National Data and Analytics Platform (NDAP). This repository ships a local SQLite metadata index of NDAP datasets, exposes the index through an MCP server, and provides on-demand dataset downloads for grounded analytical answers.

The project is designed for deep-research agents that need to discover relevant datasets, inspect indicators and dimensions, download raw observations, and produce traceable answers without hallucinating beyond available NDAP evidence.

## What This Includes

- A committed SQLite metadata index for NDAP datasets, indicators, and dimensions at `data/index.db`.
- FTS5 search over dataset names, notes, indicators, dimensions, and enrichment text.
- An MCP server with tools for dataset search, metadata lookup, sector/ministry listing, and on-demand downloads.
- A small Streamlit chat demo for OpenRouter-powered agentic dataset search.
- Utilities to harvest NDAP metadata, rebuild the index, and download raw dataset rows as CSV.
- A response template for traceable NDAP question answering in `SRIT_NDAP_QUERY_RESPONSE_TEMPLATE.md`.

## Repository Layout

```text
.
├── README.md                         # Project documentation
├── pyproject.toml                    # Python package metadata and dependencies
├── schema.py                         # Shared schema, parsers, and OpenAPI URL builder
├── ndap_client.py                    # NDAP catalogue/API client
├── ndap_auth.py                      # NDAP Cognito token refresh helper
├── harvest_metadata.py               # Harvest /v1/sourcedetails metadata
├── build_index.py                    # Build SQLite + FTS metadata index
├── query.py                          # Query layer over data/index.db
├── ndap_download.py                  # On-demand dataset downloader
├── mcp_server.py                     # FastMCP server exposing NDAP tools
├── demo_app.py                       # Streamlit chat demo using OpenRouter + SQLite search
├── scripts/
│   ├── check_index_coverage.py        # Verify catalogue coverage in data/index.db
│   └── wait_and_build_index.sh       # Wait for harvest, then rebuild index
└── data/
    ├── index.db                      # Committed SQLite metadata/search index
    ├── index_summary.json            # Committed index coverage summary
    └── fixtures/                     # Small self-test fixtures
```

Generated harvest inputs, logs, and downloaded CSVs are intentionally not committed. The committed DB is the retrieval artifact; raw observations remain on-demand local cache files.

## Local Data Model

The local SQLite database at `data/index.db` is the primary retrieval layer. It is a metadata/search index, not a full copy of NDAP.

It contains:

- `datasets`: dataset-level metadata such as ID, exact name, sector, ministry, year range, geography hints, source links, generated descriptions, and download recipe fields.
- `indicators`: indicator IDs, display names, units, scaling, descriptions, and inferred variable classes.
- `dimensions`: dimension IDs, display names, dimension types, inferred geography/time roles, and code-standard hints.
- `datasets_fts`: an FTS5 index for lexical search across dataset metadata.

Raw observations are downloaded only when needed and cached as CSV files in `data/datasets/<dataset_id>.csv`.

Current committed coverage:

- `6,621` catalogue dataset rows in `datasets`.
- `34,446` indicator metadata rows.
- `32,360` dimension metadata rows.
- `6,618` datasets with full harvested `sourcedetails` metadata.
- `3` catalogue-only fallback rows: `6576`, `7368`, `7370`. These are searchable by name/sector/ministry, but do not have indicator/dimension metadata or an OpenAPI download recipe until NDAP sourcedetails can be harvested for them.

## Setup

This project uses Python 3.10+.

```bash
uv venv ~/pyenv/ndap-deep-research-agent
source ~/pyenv/ndap-deep-research-agent/bin/activate
uv pip install -e .
cp .env.example .env
```

Fill `.env` only with credentials you actually need:

```bash
OPENROUTER_API_KEY=...
NDAP_ACCESS_TOKEN=...
NDAP_REFRESH_TOKEN=...
NDAP_TOKEN=...
```

`NDAP_REFRESH_TOKEN` is used by `harvest_metadata.py` to refresh Cognito access tokens for metadata harvests. `NDAP_TOKEN` is only needed for legacy authenticated catalogue downloads through `ndap_client.py`.

## Run The Chat Demo

The demo is a simplified, Hermes-inspired chat interface. It does not embed the full dataset catalogue into the prompt. Instead, it:

1. asks the selected OpenRouter model to plan a compact search query,
2. runs `search_datasets` against the local SQLite/FTS index,
3. fetches candidate metadata with `get_dataset_metadata`,
4. asks the model to synthesize a grounded answer from retrieved metadata only.

Launch it with:

```bash
streamlit run demo_app.py
```

Then enter:

- your OpenRouter API key,
- an OpenRouter model slug such as `openai/gpt-5.5`, `anthropic/claude-sonnet-4.6`, or another model available on your account,
- an NDAP dataset discovery question.

Example prompts:

```text
Which datasets cover slum population by city?
Find district-level school enrolment datasets by social category.
What datasets could compare crop production across states over time?
```

The demo is intentionally metadata-first. It is meant to show the agentic search loop, not to produce final statistical answers from raw observations. For factual values or comparisons, use `download_dataset` after the right dataset has been identified.

## Refresh Or Rebuild The Metadata Index

The repo already includes `data/index.db`. Rebuild it when NDAP catalogue coverage changes or when you harvest fresh `sourcedetails`.

1. Fetch or create `data/catalogue.csv`.

```bash
python - <<'PY'
from pathlib import Path
from ndap_client import NDAPClient

with NDAPClient() as client:
    _, csv_path, count = client.save_catalogue(Path("data"))
print(f"saved {count} catalogue rows to {csv_path}")
PY
```

2. Harvest sourcedetails metadata.

```bash
python harvest_metadata.py
```

For a smaller test run:

```bash
python harvest_metadata.py --limit 25
```

3. Build the SQLite/FTS index.

```bash
python build_index.py --src data/sourcedetails --catalogue data/catalogue.csv
```

The `--catalogue` argument ensures the DB includes every catalogue row. If a dataset is present in the catalogue but missing from `data/sourcedetails`, it is inserted as a catalogue-only fallback row.

4. Verify coverage.

```bash
python scripts/check_index_coverage.py
```

## Query The Index

Use `query.py` from Python:

```python
import query

matches = query.search_datasets("slum population city", limit=10)
metadata = query.get_dataset_metadata(matches[0]["id"])
```

Download raw rows for a dataset:

```bash
python ndap_download.py 9053
```

The command writes a cached CSV under `data/datasets/`.

## MCP Server

Run the MCP server:

```bash
python mcp_server.py
```

Available MCP tools:

- `search_datasets(q, sector=None, ministry=None, limit=20)`
- `get_dataset_metadata(dataset_id)`
- `list_sectors()`
- `list_ministries()`
- `download_dataset(dataset_id)`

Agents should use the metadata index for discovery, then download raw rows before making factual comparisons or calculations.

## Agent Grounding Rules

The intended agent behavior is:

- Treat `data/index.db` as the authoritative local metadata source.
- Do not stuff the dataset catalogue into prompt context. Retrieve from SQLite/FTS or MCP tools instead.
- Use `get_dataset_metadata` to inspect exact indicators and dimensions.
- Use `download_dataset` before reporting factual values.
- Abstain when NDAP evidence is unavailable or insufficient.
- Do not make unsupported causal claims or future predictions.

## Notes

NDAP endpoints and authentication behavior may change. Keep raw data, tokens, logs, and local agent state out of git. Rebuild the metadata index when NDAP catalogue coverage changes.
