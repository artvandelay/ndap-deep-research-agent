# NDAP Deep Research Agent

### ▶ Try the live demo: https://artvandelay.github.io/ndap-deep-research-agent/

A browser-based agentic chat over India's National Data and Analytics Platform (NDAP) — bring your own OpenRouter key and start asking. No install required.

---

Agent-ready tooling for exploring India's National Data and Analytics Platform (NDAP). This repository ships a local SQLite metadata index of NDAP datasets, exposes the index through an MCP server, and provides on-demand dataset downloads for grounded analytical answers.

The project is designed for deep-research agents that need to discover relevant datasets, inspect indicators and dimensions, download raw observations, and produce traceable answers without hallucinating beyond available NDAP evidence.

## What This Includes

- A committed SQLite metadata index for NDAP datasets, indicators, and dimensions at `data/index.db`.
- FTS5 search over dataset names, notes, indicators, dimensions, and enrichment text.
- An MCP server with tools for dataset search, metadata lookup, sector/ministry listing, and on-demand downloads.
- A static GitHub Pages chat demo for OpenRouter-powered agentic dataset search, with an optional CORS-proxy mode that downloads rows and computes real numbers in the browser. Each chat runs in one of two modes via a per-chat **Fast / Deep** toggle, and shows a visible agent trace. It also includes a multi-conversation sidebar with saved chat history and per-query cost/token accounting.
  - **Fast**: a single pass — plan one search → retrieve candidates → pick the single best dataset → (optionally) download it → synthesize.
  - **Deep**: a bounded research loop — decompose the question into several search angles → gather a candidate pool → select and download multiple datasets → reflect on coverage and search again to fill gaps → synthesize across all sources.
- Utilities to harvest NDAP metadata, rebuild the index, and download raw dataset rows as CSV.

## Repository Layout

```text
.
├── README.md                         # Project documentation
├── pyproject.toml                    # Python dependencies
├── ndap/                             # Core Python modules (run as python ndap/<module>.py)
│   ├── schema.py                     # Shared schema, parsers, OpenAPI URL builder
│   ├── ndap_client.py                # NDAP catalogue/API client
│   ├── ndap_auth.py                  # NDAP Cognito token refresh helper
│   ├── harvest_metadata.py           # Harvest /v1/sourcedetails metadata
│   ├── build_index.py                # Build SQLite + FTS metadata index
│   ├── query.py                      # Query layer over data/index.db
│   ├── ndap_download.py              # On-demand dataset downloader
│   └── mcp_server.py                 # FastMCP server exposing NDAP tools
├── docs/                             # GitHub Pages publish dir (see docs/README.md)
│   ├── index.html                    # Browser chat UI
│   └── assets/
│       ├── ndap_index.json           # DB-derived browser search index
│       ├── ndap_recipes.json         # Per-dataset openapi download recipes
│       └── prompts.json              # Model prompts (shared with scripts/test_queries.py)
├── proxy/                            # Cloudflare Worker CORS proxy (optional)
│   ├── worker.js
│   └── wrangler.toml
├── scripts/
│   ├── test_queries.py               # Headless regression test (same prompts as the web app)
│   ├── check_index_coverage.py       # Verify catalogue coverage in data/index.db
│   ├── export_web_index.py           # Export data/index.db for the Pages demo
│   ├── export_recipes.py             # Export download recipes for real-numbers mode
│   └── wait_and_build_index.sh       # Wait for harvest, then rebuild index
├── reference/                        # Local PDFs/specs (gitignored)
└── data/
    ├── index.db                      # Committed SQLite metadata/search index
    ├── index_summary.json            # Committed index coverage summary
    └── fixtures/                     # Small self-test fixtures
```

The web app lives in `docs/` because GitHub Pages is configured to deploy from that folder on `main` — not because it is project documentation. See [docs/README.md](docs/README.md).

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

`NDAP_REFRESH_TOKEN` is used by `ndap/harvest_metadata.py` to refresh Cognito access tokens for metadata harvests. `NDAP_TOKEN` is only needed for legacy authenticated catalogue downloads through `ndap/ndap_client.py`.

## Run The Chat Demo

The public demo runs on GitHub Pages:

https://artvandelay.github.io/ndap-deep-research-agent/

It is a simplified, Hermes-inspired chat interface. It does not embed the full dataset catalogue into the prompt. Instead, it searches a browser-friendly metadata export generated from `data/index.db` and grounds the answer in the matching records (and, in real-numbers mode, their downloaded rows).

Each chat is **Fast** or **Deep**, chosen with the toggle in the header (top of the chat). The mode is remembered per chat:

- **Fast** — one model-planned search → retrieve candidates → pick the single best dataset → (real-numbers mode) download it → synthesize a grounded answer. Lowest latency and cost.
- **Deep** — the model decomposes the question into several search angles, gathers a wider candidate pool, then selects and downloads multiple datasets, reflecting between rounds to fill gaps before synthesizing across all of them. Better for questions that need to combine datasets (e.g. rainfall × crop production), at higher latency and cost.

Open Settings (gear icon, top-right) and enter:

- your OpenRouter API key (stored only in your browser's localStorage, sent directly to OpenRouter),
- an OpenRouter model slug such as `openai/gpt-5.5`, `anthropic/claude-sonnet-4.6`, or another model on your account,
- optionally, a Data proxy URL to enable real numbers (see below),
- **Max datasets to search** — how many candidate datasets the index search surfaces for the model to choose from (default `100`; applies to both modes),
- **Deep mode: datasets to analyze** — how many datasets Deep mode will download and analyze per run (default `3`).

Example prompts:

```text
Which datasets cover slum population by city?
Find district-level school enrolment datasets by social category.
What datasets could compare crop production across states over time?
```

### Discovery mode vs. real-numbers mode

Without a Data proxy URL the demo is **discovery-only**: it identifies the right datasets but does not fetch raw values. This is the safe default and needs no extra infrastructure.

To make the demo **compute real numbers** in the browser, you need two things:

1. The download recipes asset (per-dataset openapi `API_Key`/indicators/dimensions):

   ```bash
   python scripts/export_recipes.py   # writes docs/assets/ndap_recipes.json
   ```

   Note: each recipe embeds the durable NDAP openapi key tied to the harvesting
   account. Publishing this file exposes those keys — only ship it for a demo
   where you accept that exposure.

2. A CORS proxy, because NDAP's `/v1/openapi` endpoint sends no
   `Access-Control-Allow-Origin` header (so browsers block direct calls). Deploy
   the included free Cloudflare Worker:

   ```bash
   cd proxy
   npx wrangler login
   npx wrangler deploy
   ```

   Paste the resulting `*.workers.dev` URL into Settings → "Data proxy URL". The
   Worker is stateless, stores nothing, and only forwards to `loadqa.ndapapi.com`.

In real-numbers mode the agent fetches rows for the selected dataset(s)
(paginated, capped), hands the most relevant rows to the model as CSV, and the
model computes the answer with the actual values. Fast mode uses one dataset;
Deep mode may download several and combine them. The numbers reflect the
breakdown encoded in the stored recipe (e.g. national/by-dimension); if a
requested entity isn't in those rows, the model is instructed to say so.

For large datasets only a capped sample of the most-relevant rows is shown to
the model first, but the full set of fetched rows is kept in memory. Alongside
the sample the model also gets a **data profile** (each filterable dimension and
its distinct values) and can **request more rows on demand** — by filtering on
specific dimension values (e.g. a pre-aggregated total / national row, a
particular state, city, or year) or asking for the next batch. Each request is satisfied by
re-slicing the in-memory rows (no extra network calls), bounded to a few rounds.
This lets the agent reach rows that keyword relevance alone would miss instead of
guessing or wrongly aggregating a partial sample.

### Conversations and multi-turn memory

The demo keeps a compressed memory of the last few turns (question + trimmed
answer + dataset used) and feeds it into planning, dataset selection, and
synthesis, so elliptical follow-ups like "break that down by sex" stay on the
same topic. It is intentionally small (a few turns) to keep token use low.

Conversations are saved per-chat in your browser's localStorage and listed in
the left **sidebar**, grouped by recency (Today / Yesterday / Previous 7/30
days). Switch between past chats, start a fresh one with **New chat**, or delete
any conversation; the active chat reopens on reload. The sidebar collapses to an
off-canvas drawer on small screens. Everything stays in your browser — nothing
is uploaded.

On credit, context, auth, or proxy errors the demo shows a short, actionable
message instead of failing hard.

To refresh the static Pages assets after rebuilding `data/index.db`:

```bash
python scripts/export_web_index.py
python scripts/export_recipes.py    # only if using real-numbers mode
```

## Refresh Or Rebuild The Metadata Index

The repo already includes `data/index.db`. Rebuild it when NDAP catalogue coverage changes or when you harvest fresh `sourcedetails`.

1. Fetch or create `data/catalogue.csv`.

```bash
python - <<'PY'
import sys
sys.path.insert(0, "ndap")
from pathlib import Path
from ndap_client import NDAPClient

with NDAPClient() as client:
    _, csv_path, count = client.save_catalogue(Path("data"))
print(f"saved {count} catalogue rows to {csv_path}")
PY
```

2. Harvest sourcedetails metadata.

```bash
python ndap/harvest_metadata.py
```

For a smaller test run:

```bash
python ndap/harvest_metadata.py --limit 25
```

3. Build the SQLite/FTS index.

```bash
python ndap/build_index.py --src data/sourcedetails --catalogue data/catalogue.csv
```

The `--catalogue` argument ensures the DB includes every catalogue row. If a dataset is present in the catalogue but missing from `data/sourcedetails`, it is inserted as a catalogue-only fallback row.

4. Verify coverage.

```bash
python scripts/check_index_coverage.py
```

## Query The Index

Use `ndap/query.py` from Python (add `ndap/` to `sys.path`, or run from repo root):

```python
import sys
sys.path.insert(0, "ndap")
import query

matches = query.search_datasets("slum population city", limit=10)
metadata = query.get_dataset_metadata(matches[0]["id"])
```

Download raw rows for a dataset:

```bash
python ndap/ndap_download.py 9053
```

The command writes a cached CSV under `data/datasets/`.

## MCP Server

Run the MCP server:

```bash
python ndap/mcp_server.py
```

If your MCP client config points at this server, use the path `ndap/mcp_server.py` (repo root as working directory).

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
