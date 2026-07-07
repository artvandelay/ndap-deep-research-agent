# GitHub Pages site

This folder is the **published web app** for the NDAP Deep Research Agent.

GitHub Pages is configured to deploy from `/docs` on `main`, so the live demo is served directly from here:

https://artvandelay.github.io/ndap-deep-research-agent/

Do not rename or move this folder without updating the Pages source in the repo settings (or switching to a GitHub Actions deploy workflow).

## Contents

| Path | Role |
|------|------|
| `index.html` | Browser chat UI (Fast / Deep depth, Objective / Judgemental personality, per-chat locking, Stop button, and run deadlines) |
| `assets/ndap_index.json` | Metadata search index exported from `data/index.db` |
| `assets/ndap_recipes.json` | Per-dataset openapi download recipes (real-numbers mode) |
| `assets/prompts.json` | Single source of truth for all model-facing prompts (shared with `scripts/test_queries.py`) |

Refresh the JSON assets after rebuilding the index:

```bash
python scripts/export_web_index.py
python scripts/export_recipes.py
```

The published app is fully browser-side. In real-numbers mode the chat runs a
native tool-calling loop over browser-local tools
(search/inspect/download/filter/profile/aggregate) to reach the answer from the
downloaded rows. While an answer is running, the Send
button changes to Stop so the current OpenRouter/proxy request can be aborted.
Fast-depth runs have a 2-minute wall-clock ceiling; Deep-depth runs have a 5-minute ceiling. The chosen depth and personality are locked after the first message in a chat.

Settings takes two model slugs: a **Small model** (does search, planning, dataset selection, and the browser-local tool loop; cheap/fast is fine, e.g. `openai/gpt-5.4-nano`) and a **Large model** (writes every final answer; use a stronger model, e.g. `anthropic/claude-sonnet-4.6`). Personality only changes the answer's voice and temperature — it no longer picks a different model; the Large model always writes the answer.
