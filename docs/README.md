# GitHub Pages site

This folder is the **published web app** for the NDAP Deep Research Agent.

GitHub Pages is configured to deploy from `/docs` on `main`, so the live demo is served directly from here:

https://artvandelay.github.io/ndap-deep-research-agent/

Do not rename or move this folder without updating the Pages source in the repo settings (or switching to a GitHub Actions deploy workflow).

## Contents

| Path | Role |
|------|------|
| `index.html` | Browser chat UI (Fast / Deep modes) |
| `assets/ndap_index.json` | Metadata search index exported from `data/index.db` |
| `assets/ndap_recipes.json` | Per-dataset openapi download recipes (real-numbers mode) |
| `assets/prompts.json` | Single source of truth for all model-facing prompts (shared with `scripts/test_queries.py`) |

Refresh the JSON assets after rebuilding the index:

```bash
python scripts/export_web_index.py
python scripts/export_recipes.py
```
