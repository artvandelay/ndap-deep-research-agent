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
- A static GitHub Pages chat demo for OpenRouter-powered agentic dataset search, with an optional CORS-proxy mode that downloads rows and computes real numbers in the browser. Each chat starts with two locked choices — **Depth** (`Fast` / `Deep`) and **Personality** (`Objective` / `Judgemental`) — and shows a visible agent trace. Long runs can be stopped from the composer and have depth-specific wall-clock ceilings. It also includes a multi-conversation sidebar with saved chat history and per-query cost/token accounting.
  - **Fast**: a single pass — plan one search → retrieve candidates → pick the single best dataset → (optionally) download it → synthesize.
  - **Deep**: a bounded research loop — decompose the question into several search angles → gather a candidate pool → select and download multiple datasets → reflect on coverage and search again to fill gaps → synthesize across all sources.
  - **Judgemental**: a sharper personality layer — it keeps the selected evidence depth, then makes evidence-grounded calls on patterns, correlations, gaps, caveats, skepticism, and forecasts. Every figure is still NDAP-only.
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

Each chat starts with a **Depth** choice (`Fast` or `Deep`) and a **Personality** choice (`Objective` or `Judgemental`), chosen before the first message. Both choices then lock for that conversation, and each turn records the depth, personality, and model used:

- **Fast** — one model-planned search → retrieve candidates → pick the single best dataset → (real-numbers mode) download it → synthesize a grounded answer. Lowest latency and cost.
- **Deep** — the model decomposes the question into several search angles, gathers a wider candidate pool, then selects and downloads multiple datasets, reflecting between rounds to fill gaps before synthesizing across all of them. Better for questions that need to combine datasets (e.g. rainfall × crop production), at higher latency and cost.
- **Objective** — concise, sober, answer-first writing.
- **Judgemental** — the investigative data-journalist persona: it follows the user's requested format and can make judgement calls, correlations, gap calls, skepticism, and forecasts when the supplied NDAP evidence supports them. Answers are opinionated in analysis but never creative with the numbers.

Personality only changes the answer's voice and temperature — it no longer selects a different model. The Large model always writes the final answer; the Small model always drives search, planning, dataset selection, and the browser-local tool loop.

While an answer is running, the Send button becomes **Stop**. Stopping cancels the active model/data request, leaves any partial streamed answer visible, and avoids saving the interrupted turn. Runs also have overall wall-clock ceilings: Fast depth stops after 2 minutes; Deep depth stops after 5 minutes, with a timeout note instead of hanging indefinitely.

Open Settings (gear icon, top-right) and enter:

- your OpenRouter API key (stored only in your browser's localStorage, sent directly to OpenRouter),
- a **Small model** slug (does search, planning, dataset selection, and the browser-local tool loop; cheap/fast is fine) such as `openai/gpt-5.4-nano`,
- a **Large model** slug (writes every final answer; use a stronger model) such as `anthropic/claude-sonnet-4.6`,
- optionally, a Data proxy URL to enable real numbers (see below),
- **Max datasets to search** — how many candidate datasets the index search surfaces for the model to choose from (default `100`; applies to both modes),
- **Deep depth: datasets to analyze** — how many datasets Deep will download and analyze per run (default `3`).

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
(paginated, capped) and then drives a **native tool-calling loop** to reach the
answer with the actual values. For each downloaded dataset the model receives a
small **preview** of the rows plus a **data profile** — each filterable
dimension and its distinct values — and works from there. Fast mode starts from
the top matching dataset, but the loop may pull in more within its budgets; Deep
mode reads several and combines them. The numbers reflect the breakdown actually
present in the fetched rows; if a requested entity isn't there, the model is
instructed to say so.

From the preview and profile the model drives a bounded set of **browser-local
tools** via native tool-calling:

- `search_datasets` / `inspect_dataset` / `download_dataset` — find and pull
  additional datasets.
- `preview_more` / `filter_rows` / `search_rows` — reach more rows by paging,
  filtering on specific dimension values (e.g. a national/total row, a
  particular state, city, or year), or searching text.
- `profile_column` — list the distinct values of a column.
- `compute_aggregate` — sum / avg / min / max / count, optionally with a
  group-by, computed over the rows.

Most row tools re-slice data that's already been downloaded into memory, but
`download_dataset` fetches through the proxy, so the loop can make additional
network calls when it needs a new dataset. The whole loop is bounded by per-run
step, row, and download budgets. This lets the agent reach rows and rollups that
keyword relevance alone would miss instead of guessing or wrongly aggregating a
partial sample.

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
