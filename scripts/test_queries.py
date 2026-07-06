#!/usr/bin/env python3
"""
NDAP query regression TEST — a headless mirror of the docs/index.html Fast, Deep & Scoop
pipelines, used to check answer quality without a browser.

Why this file exists (read before editing):
  * It loads its prompts from docs/assets/prompts.json — the SAME file the web app
    (docs/index.html) loads. There is ONE source of truth for prompt prose, so the
    app and this test can never drift apart. Do NOT paste prompt text in here; add
    or edit it in prompts.json and both sides update together.
  * Run with no args to execute the built-in regression suite (the queries we use to
    catch known failures, with light ground-truth checks). Or pass --query/--mode/
    --homepage/--srit for ad-hoc runs.

Usage:
  python scripts/test_queries.py                         # built-in regression suite
  python scripts/test_queries.py --mode deep --query "…" # ad-hoc, repeatable --query
  python scripts/test_queries.py --homepage --mode deep  # the 4 homepage chips
  python scripts/test_queries.py --srit path/to.md --mode fast

Requires OPENROUTER_API_KEY in the repo-root .env.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
KEY = [l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("OPENROUTER_API_KEY=")][0]

SEARCH_MAX = 100
DEEP_DOWNLOADS = 3
DEEP_MAX_ITERS = 3
FAST_METADATA_CANDIDATES = 12
AGENT_PREVIEW_ROWS = 10
MAX_AGENT_STEPS = 10
MAX_AGENT_ROWS_PER_STEP = 1000
MAX_AGENT_ROWS_TOTAL = 3500
MAX_AGENT_DOWNLOADS = 6
MAX_LLM_ROWS = AGENT_PREVIEW_ROWS
MAX_PAGES = 8
PAGE_SIZE = 1000
MAX_DRILL_ITERS = MAX_AGENT_STEPS
DRILL_ROWS = 500
PROFILE_VALUES_CAP = 40

INDEX = json.loads((DOCS / "assets/ndap_index.json").read_text())
RECIPES = json.loads((DOCS / "assets/ndap_recipes.json").read_text())
# Single source of truth for prompts — shared verbatim with docs/index.html.
PROMPTS = json.loads((DOCS / "assets/prompts.json").read_text())


def P(key: str, **params) -> str:
    """Resolve a prompt by key; replace {{token}} with another prompt entry or a param.
    Mirrors the P() helper in docs/index.html (one pass; referenced entries hold no tokens)."""
    raw = PROMPTS.get(key, "")
    table = {**PROMPTS, **{k: str(v) for k, v in params.items()}}
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(table.get(m.group(1), "")), raw)


# ---- Built-in regression suite: the queries we test, with known-good signals. ----
# expect_any = answer should contain at least one of these substrings (soft check;
# LLM phrasing varies, so a FAIL is a prompt to eyeball the saved JSON, not a hard error).
SUITE = [
    {"label": "slum-2011-total", "mode": "deep",
     "q": "What was India's total slum population in 2011?",
     "expect_any": ["65,494,604", "65494604", "65.49"]},
    {"label": "slum-2001-vs-2011-by-sex", "mode": "deep",
     "q": "Compare India's total slum population in 2001 vs 2011 and break it down by sex, with the change and growth rate.",
     "expect_any": ["65,494,604", "65494604"]},
    {"label": "national-female-lfpr", "mode": "deep",
     "q": "what's india's latest female labour force participation rate?",
     "expect_any": ["41.7"]},
    {"label": "mumbai-vs-kolkata-slum-share", "mode": "deep",
     "q": "Mumbai vs Kolkata, which has a higher slum population share?",
     "expect_any": ["not available", "Low Confidence", "Unverified", "city-level", "cannot", "no dataset"]},
]

HOMEPAGE_CHIPS = [
    "Compare India's total slum population in 2001 vs 2011 and break it down by sex, with the change and growth rate.",
    "Which NDAP datasets would I join to correlate state-level rainfall with crop production over time, and what's the geography/time overlap?",
    "Study the link between district literacy and school enrolment by social category — identify the datasets and how to combine them.",
    "Track how the urban slum share of population shifted from 2001 to 2011 and which datasets reveal the state-level drivers.",
]


def clean_query(q: str) -> str:
    q = q.strip()
    q = re.sub(r"^#+\s*", "", q)
    q = re.sub(r"^\*\*|\*\*$", "", q)
    q = re.sub(r"\\\.", ".", q)
    q = re.sub(r"\\\-\s*", "- ", q)
    return q.strip()


def parse_srit_queries(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    queries: list[str] = []
    for block in re.split(r"\n# Query \d+\n", text):
        m = re.search(r"## \*\*Query\*\*\s*\n\n(.*?)(?=\n## \*\*Generated Response\*\*)", block, re.S)
        if m:
            queries.append(clean_query(m.group(1)))
            continue
        m2 = re.search(r"# \*\*QUERY ID: \d+\*\*\s*\n\n## (.+?)\n\n## \*\*Generated Response\*\*", block, re.S)
        if m2 and "Query" not in m2.group(1):
            queries.append(clean_query(m2.group(1)))
    return queries


def chat(model: str, messages: list, temperature: float = 0, max_tokens: int = 2000) -> str:
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    d = json.load(urllib.request.urlopen(req, timeout=180))
    return d["choices"][0]["message"]["content"]


def extract_json(text: str):
    s = str(text)
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no json")
    return json.loads(s[a : b + 1])


def tokenize(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", str(t or "").lower()) if len(w) > 2]


def search_index(query: str, limit: int):
    terms = tokenize(query)
    if not terms:
        return []
    scored = []
    for it in INDEX["items"]:
        name = str(it["name"]).lower()
        desc = str(it["description"]).lower()
        sect = str(it["sector"]).lower()
        mini = str(it["ministry"]).lower()
        s = sum(8 for t in terms if t in name) + sum(5 for t in terms if t in desc) + sum(3 for t in terms if t in sect) + sum(2 for t in terms if t in mini)
        if s:
            scored.append((s, it))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [it for _, it in scored[:limit]]


def search_pool(queries: list[str], mx: int):
    ranked = [search_index(q, mx) for q in queries]
    seen: dict = {}
    rank = 0
    while len(seen) < mx:
        progressed = False
        for lst in ranked:
            if rank < len(lst):
                progressed = True
                it = lst[rank]
                if it["id"] not in seen:
                    seen[it["id"]] = it
                if len(seen) >= mx:
                    break
        if not progressed:
            break
        rank += 1
    return list(seen.values())[:mx]


def slim(lst):
    return [{"id": c["id"], "name": c["name"], "grain": c.get("grain") or "", "dims": c.get("dims") or [], "years": c.get("years"), "about": c["description"]} for c in lst]


def plan_search(model: str, question: str):
    msgs = [
        {"role": "system", "content": P("plan_search_sys")},
        {"role": "user", "content": f"Current question:\n{question}\n\nReturn exactly: {{\"search_query\":\"...\",\"reason\":\"...\"}}"},
    ]
    try:
        p = extract_json(chat(model, msgs, 0, 400))
        return str(p.get("search_query") or question), str(p.get("reason") or "")
    except Exception as e:
        return question, f"fallback: {e}"


def plan_deep(model: str, question: str):
    msgs = [
        {"role": "system", "content": P("plan_deep_sys")},
        {"role": "user", "content": f"Current question:\n{question}\n\nReturn exactly: {{\"search_queries\":[\"...\"],\"sub_questions\":[\"...\"],\"reason\":\"...\"}}"},
    ]
    try:
        p = extract_json(chat(model, msgs, 0, 600))
        qs = [str(x).strip() for x in p.get("search_queries", []) if str(x).strip()] or [question]
        return qs[:4], str(p.get("reason") or "")
    except Exception as e:
        return [question], f"fallback: {e}"


def select_datasets(model: str, question: str, pool, already: list[str], n: int):
    have = f"Already downloaded: {', '.join(already)}. Pick only NEW datasets that add information still missing.\n" if already else ""
    msgs = [
        {"role": "system", "content": P("select_datasets_sys", n=n)},
        {"role": "user", "content": f"{have}Current question:\n{question}\n\nCandidates:\n{json.dumps(slim(pool))}\n\nReturn exactly: {{\"dataset_ids\":[<id>, ...],\"reason\":\"...\"}}"},
    ]
    fresh = lambda c: str(c["id"]) not in already
    try:
        p = extract_json(chat(model, msgs, 0, 500))
        picks = []
        for i in [str(x) for x in p.get("dataset_ids", [])]:
            m = next((c for c in pool if str(c["id"]) == i), None)
            if m and m not in picks and fresh(m):
                picks.append(m)
        if not picks:
            fn = next((c for c in pool if fresh(c)), None)
            if fn:
                picks.append(fn)
        return picks[:n], str(p.get("reason") or "")
    except Exception as e:
        return [c for c in pool if fresh(c)][:n], f"fallback: {e}"


def reflect(model: str, question: str, collected):
    summ = "\n".join(f"Dataset {c['id']} ({c['name']}); columns: {', '.join(c['columns'])}; rows sampled: {len(c['used'])}" for c in collected)
    msgs = [
        {"role": "system", "content": P("reflect_sys")},
        {"role": "user", "content": f"Current question:\n{question}\n\nGathered so far:\n{summ or '(nothing downloaded yet)'}\n\nReturn exactly: {{\"sufficient\":true|false,\"missing\":\"...\",\"next_query\":\"...\"}}"},
    ]
    try:
        p = extract_json(chat(model, msgs, 0, 400))
        return bool(p.get("sufficient")), str(p.get("next_query") or "").strip()
    except Exception:
        return True, ""


def cell_value(v):
    if isinstance(v, dict):
        if v.get("avg") is not None:
            return v["avg"]
        if v.get("value") is not None:
            return v["value"]
        if v.get("sum") is not None:
            return v["sum"]
        return ""
    return v


def fetch_rows(dsid):
    rec = RECIPES["recipes"][str(dsid)]
    base = RECIPES["base"]
    cols, rows, trunc = [], [], False
    for page in range(1, MAX_PAGES + 1):
        url = f"{base}?API_Key={urllib.parse.quote(rec['k'])}&ind={rec['i']}&dim={rec['d']}&pageno={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        payload = json.load(urllib.request.urlopen(req, timeout=90))
        if payload.get("IsError"):
            raise RuntimeError(payload.get("Message"))
        if not cols:
            cols = [str(h.get("ID") or h.get("DisplayName") or "").strip() for h in payload.get("Headers", {}).get("Items", []) if (h.get("ID") or h.get("DisplayName"))]
        pr = payload.get("Data", [])
        rows += pr
        if len(pr) < PAGE_SIZE:
            break
        if page == MAX_PAGES:
            trunc = True
    return cols, rows, trunc


def select_relevant(rows, question, mx):
    if len(rows) <= mx:
        return rows
    terms = tokenize(question)
    sc = []
    for r in rows:
        blob = " ".join(str(cell_value(v)) for v in r.values()).lower()
        sc.append((sum(1 for t in terms if t in blob), r))
    sc.sort(key=lambda x: -x[0])
    return [r for _, r in sc[:mx]]


def to_csv(cols, rows):
    def esc(v):
        s = str(v if v is not None else "")
        return '"' + s.replace('"', '""') + '"' if re.search(r'[",\n]', s) else s

    return cols and ("\n".join([",".join(cols)] + [",".join(esc(cell_value(r.get(c))) for c in cols) for r in rows]))


def rows_note(c):
    partial = len(c["used"]) < len(c["rows"])
    flag = (
        "TRUNCATED at the fetch cap — more rows exist, dataset is INCOMPLETE"
        if c["truncated"]
        else ("PARTIAL filtered subset" if partial else "COMPLETE dataset (all rows present)")
    )
    counts = f"{len(c['used'])} of {len(c['rows'])}{'+' if c['truncated'] else ''} fetched" if partial else f"{len(c['used'])} (all rows)"
    return f"Rows provided: {counts} — {flag}"


def download_for_llm(pick, question, row_cap):
    cols, rows, trunc = fetch_rows(pick["id"])
    used = rows[:AGENT_PREVIEW_ROWS]
    return {"id": pick["id"], "name": pick["name"], "columns": cols, "rows": rows, "used": used, "csv": to_csv(cols, used), "truncated": trunc, "_sent": {id(r) for r in used}}


def metadata_messages(question, candidates, mode="fast"):
    return [
        {"role": "system", "content": P("scoop_metadata_sys" if mode == "scoop" else "metadata_sys")},
        {"role": "user", "content": f"Current question:\n{question}\n\nRetrieved candidate metadata (JSON):\n{json.dumps(candidates, indent=2)}\n\nGive a concise, grounded answer: likely dataset(s), why they match, and the next action."},
    ]


def dataset_profile_text(c):
    lines = []
    for col in c["columns"]:
        is_dim = True
        vals = []
        seen = set()
        for r in c["rows"]:
            raw = r.get(col)
            if isinstance(raw, dict):
                is_dim = False
                break
            v = str(cell_value(raw) if raw is not None else "").strip()
            if v and v not in seen:
                seen.add(v)
                vals.append(v)
        if is_dim:
            shown = vals[:PROFILE_VALUES_CAP]
            extra = f" (+{len(vals) - len(shown)} more)" if len(vals) > len(shown) else ""
            lines.append(f"- {col}: {' | '.join(shown)}{extra}")
    return f"Total rows available: {len(c['rows'])}{'+' if c['truncated'] else ''}\nFilterable dimensions (distinct values):\n" + "\n".join(lines)


def clamp_int(v, lo, hi, default):
    try:
        n = int(float(v))
    except Exception:
        return default
    return max(lo, min(hi, n))


def dataset_by_id(dataset_id):
    return next((it for it in INDEX["items"] if str(it["id"]) == str(dataset_id)), None)


def match_where(row, columns, where):
    if not isinstance(where, dict):
        return True
    entries = [(k, v) for k, v in where.items() if k in columns]
    if not entries:
        return True
    for k, v in entries:
        cell = str(cell_value(row.get(k)) if row.get(k) is not None else "").lower()
        wanted = v if isinstance(v, list) else [v]
        if not any(str(x).lower() in cell for x in wanted):
            return False
    return True


def match_query(row, columns, query, scoped_columns=None):
    terms = tokenize(query)
    if not terms:
        return True
    cols = [c for c in (scoped_columns or columns) if c in columns] or columns
    blob = " ".join(str(cell_value(row.get(c))) for c in cols).lower()
    return all(t in blob for t in terms)


def filter_rows_for_action(c, action):
    rows = [r for r in c["rows"] if match_where(r, c["columns"], action.get("where"))]
    return [r for r in rows if match_query(r, c["columns"], action.get("query") or action.get("search"), action.get("columns"))]


def choose_rows(c, action, state):
    sent = c.setdefault("_sent", {id(r) for r in c["used"]})
    requested = clamp_int(action.get("limit") or action.get("n"), 1, MAX_AGENT_ROWS_PER_STEP, DRILL_ROWS)
    remaining = max(0, MAX_AGENT_ROWS_TOTAL - state["rows_returned"])
    limit = min(requested, remaining)
    if not limit:
        return []
    pool = c["rows"] if action.get("tool") == "preview_more" and not action.get("where") and not (action.get("query") or action.get("search")) else filter_rows_for_action(c, action)
    offset = clamp_int(action.get("offset"), 0, max(0, len(pool) - 1), 0)
    sliced = pool[offset:]
    unseen = [r for r in sliced if id(r) not in sent]
    chosen = (unseen or sliced)[:limit]
    sent.update(id(r) for r in chosen)
    state["rows_returned"] += len(chosen)
    return chosen


def profile_column(c, column):
    if column not in c["columns"]:
        return f"Column not found: {column}"
    vals, seen = [], set()
    for r in c["rows"]:
        v = str(cell_value(r.get(column)) if r.get(column) is not None else "").strip()
        if v and v not in seen:
            seen.add(v)
            vals.append(v)
    shown = vals[:200]
    return json.dumps({"dataset": c["id"], "column": column, "distinct_count": len(vals), "values": shown, "truncated": len(vals) > len(shown)}, indent=2, ensure_ascii=False)


def numeric_value(v):
    try:
        s = str(cell_value(v) if v is not None else "").replace(",", "")
        n = float(s)
        return n
    except Exception:
        return None


def infer_numeric_columns(c, rows):
    out = []
    for col in c["columns"]:
        if any(numeric_value(r.get(col)) is not None for r in rows):
            out.append(col)
        if len(out) >= 4:
            break
    return out


def compute_aggregate(c, action):
    rows = filter_rows_for_action(c, action)
    group_by = [str(x) for x in (action.get("group_by") or action.get("groupBy") or []) if str(x) in c["columns"]][:3]
    metrics = action.get("metrics") if isinstance(action.get("metrics"), list) else []
    if not metrics:
        metrics = [{"column": col, "op": "avg"} for col in infer_numeric_columns(c, rows)]
    cleaned = []
    for m in metrics[:8]:
        col = str(m.get("column", ""))
        op = str(m.get("op", "avg")).lower()
        if op == "count" or col in c["columns"]:
            cleaned.append({"column": col, "op": op})
    groups = {}
    for row in rows:
        key = tuple(str(cell_value(row.get(col)) if row.get(col) is not None else "") for col in group_by) if group_by else ("__all__",)
        groups.setdefault(key, []).append(row)
    out = []
    for key, group_rows in groups.items():
        rec = {}
        if group_by:
            for col, val in zip(group_by, key):
                rec[col] = val
        rec["row_count"] = len(group_rows)
        for m in cleaned:
            if m["op"] == "count":
                rec[f"count{('_' + m['column']) if m['column'] else ''}"] = len(group_rows)
                continue
            nums = [numeric_value(r.get(m["column"])) for r in group_rows]
            nums = [n for n in nums if n is not None]
            if not nums:
                rec[f"{m['op']}_{m['column']}"] = None
            elif m["op"] == "sum":
                rec[f"sum_{m['column']}"] = sum(nums)
            elif m["op"] == "min":
                rec[f"min_{m['column']}"] = min(nums)
            elif m["op"] == "max":
                rec[f"max_{m['column']}"] = max(nums)
            else:
                rec[f"avg_{m['column']}"] = sum(nums) / len(nums)
        out.append(rec)
    limit = clamp_int(action.get("limit"), 1, 200, 80)
    return json.dumps({"dataset": c["id"], "matched_rows": len(rows), "grouped_by": group_by, "results": out[:limit], "truncated": len(out) > limit}, indent=2, ensure_ascii=False)


def parse_agent_action(text):
    try:
        o = extract_json(text)
        if isinstance(o, dict) and isinstance(o.get("fetch_rows"), dict):
            return {"tool": "filter_rows", **o["fetch_rows"]}
        if isinstance(o, dict) and (o.get("tool") or o.get("action")):
            o["tool"] = str(o.get("tool") or o.get("action"))
            return o
    except Exception:
        pass
    return None


def data_initial_messages(question, collected, mode):
    sys = P("data_sys_multi") if mode == "deep" else (P("scoop_sys_single") if mode == "scoop" else P("data_sys_single"))
    blocks = []
    for c in collected:
        hidden = len(c["used"]) < len(c["rows"])
        profile = ("\n" + dataset_profile_text(c)) if hidden else ""
        label = f"Preview rows ({len(c['used'])} of {len(c['rows'])}{'+' if c['truncated'] else ''}, CSV):" if hidden else "All rows (CSV):"
        blocks.append(f"Dataset {c['id']} — {c['name']}\nColumns: {', '.join(c['columns'])}\n{rows_note(c)}{profile}\n\n{label}\n{c['csv']}")
    body = ("\n\n" + "=" * 40 + "\n\n").join(blocks)
    protocol = P(
        "agentic_data_protocol",
        max_agent_steps=MAX_AGENT_STEPS,
        max_rows_per_step=MAX_AGENT_ROWS_PER_STEP,
        max_rows_total=MAX_AGENT_ROWS_TOTAL,
        max_agent_downloads=MAX_AGENT_DOWNLOADS,
    )
    lead = f"You have {len(collected)} NDAP datasets below — use them together as needed:\n\n" if len(collected) > 1 else ""
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"Current question:\n{question}\n\n{lead}{body}{protocol}"},
    ]


def execute_agent_action(action, collected, state):
    tool = str(action.get("tool") or action.get("action") or "").lower()
    if tool == "search_datasets":
        query = str(action.get("query") or action.get("q") or "").strip()
        limit = clamp_int(action.get("limit"), 1, 50, 12)
        matches = search_index(query, min(SEARCH_MAX, limit)) if query else []
        return {"tool": tool, "query": query, "rows": 0, "observation": f"Observation: search_datasets returned {len(matches)} candidates:\n{json.dumps(slim(matches), indent=2, ensure_ascii=False)}"}
    if tool == "inspect_dataset":
        item = dataset_by_id(action.get("dataset") or action.get("dataset_id"))
        return {"tool": tool, "rows": 0, "observation": f"Observation: inspect_dataset:\n{json.dumps(item, indent=2, ensure_ascii=False) if item else 'dataset not found'}"}
    if tool == "download_dataset":
        did = action.get("dataset") or action.get("dataset_id")
        existing = next((c for c in collected if str(c["id"]) == str(did)), None)
        if existing:
            return {"tool": tool, "dataset": did, "rows": 0, "observation": f"Observation: dataset {did} is already downloaded.\n{dataset_profile_text(existing)}"}
        if state["downloads"] >= MAX_AGENT_DOWNLOADS:
            return {"tool": tool, "dataset": did, "rows": 0, "observation": f"Observation: download budget exhausted ({MAX_AGENT_DOWNLOADS} datasets)."}
        item = dataset_by_id(did)
        if not item:
            return {"tool": tool, "dataset": did, "rows": 0, "observation": f"Observation: dataset not found: {did}"}
        got = download_for_llm(item, "", AGENT_PREVIEW_ROWS)
        collected.append(got)
        state["downloads"] += 1
        state["rows_returned"] += len(got["used"])
        return {"tool": tool, "dataset": did, "rows": len(got["used"]), "observation": f"Observation: downloaded dataset {got['id']} — {got['name']}\nColumns: {', '.join(got['columns'])}\n{rows_note(got)}\n{dataset_profile_text(got)}\n\nPreview rows ({len(got['used'])}, CSV):\n{got['csv']}"}

    ds = next((c for c in collected if str(c["id"]) == str(action.get("dataset") or action.get("dataset_id"))), None)
    if not ds:
        return {"tool": tool, "rows": 0, "observation": f"Observation: {tool} requires a downloaded dataset; request download_dataset first."}
    if tool == "profile_column":
        return {"tool": tool, "dataset": ds["id"], "rows": 0, "observation": "Observation: profile_column:\n" + profile_column(ds, str(action.get("column") or ""))}
    if tool == "compute_aggregate":
        return {"tool": tool, "dataset": ds["id"], "rows": 0, "observation": "Observation: compute_aggregate:\n" + compute_aggregate(ds, action)}
    if tool in {"preview_more", "filter_rows", "search_rows", "fetch_rows"}:
        rows = choose_rows(ds, action, state)
        csv = to_csv(ds["columns"], rows) if rows else "(no rows matched)"
        where = f" where {json.dumps(action.get('where'), ensure_ascii=False)}" if isinstance(action.get("where"), dict) else ""
        q = f" query={action.get('query') or action.get('search')}" if (action.get("query") or action.get("search")) else ""
        return {"tool": tool, "dataset": ds["id"], "rows": len(rows), "where": action.get("where"), "query": action.get("query") or action.get("search"), "observation": f"Observation: {tool} returned {len(rows)} rows from dataset {ds['id']}{where}{q}:\n{csv}"}
    return {"tool": tool, "rows": 0, "observation": f'Observation: unknown tool "{tool}".'}


def synthesize_with_drilldown(model, question, collected, mode):
    messages = data_initial_messages(question, collected, mode)
    drills = []
    state = {"downloads": len(collected), "rows_returned": sum(len(c["used"]) for c in collected)}
    ask = P("agentic_data_ask") or P("drill_ask")
    for _ in range(MAX_AGENT_STEPS):
        messages.append({"role": "user", "content": ask})
        resp = chat(model, messages, 0, 700)
        action = parse_agent_action(resp)
        if not action or str(action.get("tool", "")).lower() in {"ready", "answer", "final_answer"}:
            messages.pop()
            break
        messages.append({"role": "assistant", "content": resp})
        obs = execute_agent_action(action, collected, state)
        drills.append({k: v for k, v in obs.items() if k != "observation"})
        messages.append({"role": "user", "content": obs["observation"]})
    answer_ask = P("scoop_answer_ask") if mode == "scoop" else P("answer_ask")
    answer_temp = 0.9 if mode == "scoop" else 0
    answer_max = 3000
    messages.append({"role": "user", "content": answer_ask})
    final = chat(model, messages, answer_temp, answer_max)
    stray = parse_agent_action(final)
    for _ in range(3):
        if not stray:
            break
        obs = execute_agent_action(stray, collected, state)
        drills.append({k: v for k, v in obs.items() if k != "observation"} | {"phase": "final"})
        messages.append({"role": "assistant", "content": final})
        messages.append({"role": "user", "content": f"{obs['observation']}\n\n{answer_ask}"})
        final = chat(model, messages, answer_temp, answer_max)
        stray = parse_agent_action(final)
    return final, drills


def gather_fast(model: str, question: str, mode: str = "fast") -> dict:
    trace = {"mode": mode}
    sq, reason = plan_search(model, question)
    trace["search_query"] = sq
    trace["plan_reason"] = reason
    candidates = search_index(sq, SEARCH_MAX)
    trace["pool_size"] = len(candidates)
    if not candidates:
        trace["status"] = "no_candidates"
        return trace
    picks, sel_reason = select_datasets(model, question, candidates, [], 1)
    trace["select_reason"] = sel_reason
    pick = picks[0] if picks else candidates[0]
    trace["dataset_ids"] = [pick["id"]]
    try:
        got = download_for_llm(pick, question, MAX_LLM_ROWS)
        trace["rows"] = f"{len(got['used'])}/{len(got['rows'])}{'+' if got['truncated'] else ''}"
        trace["completeness"] = rows_note(got)
        trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, [got], mode)
        trace["status"] = "ok"
    except Exception as e:
        trace["status"] = "download_failed"
        trace["error"] = str(e)[:200]
        trace["answer"] = chat(model, metadata_messages(question, slim(candidates[:FAST_METADATA_CANDIDATES]), mode), 0.9 if mode == "scoop" else 0, 2000)
    return trace


def gather_deep(model: str, question: str, mode: str = "deep") -> dict:
    trace = {"mode": mode}
    queries, reason = plan_deep(model, question)
    trace["plan_queries"] = queries
    trace["plan_reason"] = reason
    pool = search_pool([question] + queries, SEARCH_MAX)
    trace["pool_size"] = len(pool)
    if not pool:
        trace["status"] = "no_candidates"
        return trace
    collected, done_ids = [], []
    for it in range(1, DEEP_MAX_ITERS + 1):
        if len(collected) >= DEEP_DOWNLOADS:
            break
        remaining = DEEP_DOWNLOADS - len(collected)
        picks, sel_reason = select_datasets(model, question, pool, done_ids, remaining)
        trace[f"select_r{it}_reason"] = sel_reason
        if not picks:
            break
        for p in picks:
            if len(collected) >= DEEP_DOWNLOADS:
                break
            done_ids.append(str(p["id"]))
            try:
                collected.append(download_for_llm(p, question, MAX_LLM_ROWS))
            except Exception as e:
                trace.setdefault("download_errors", []).append(f"{p['id']}: {str(e)[:80]}")
        if len(collected) >= DEEP_DOWNLOADS or it >= DEEP_MAX_ITERS:
            break
        suff, nq = reflect(model, question, collected)
        trace[f"reflect_r{it}"] = {"sufficient": suff, "next_query": nq}
        if suff or not nq:
            break
        more = search_index(nq, SEARCH_MAX)
        added = [m for m in more if all(x["id"] != m["id"] for x in pool)]
        pool.extend(added)
        if not added:
            break
    trace["dataset_ids"] = [c["id"] for c in collected]
    trace["completeness"] = [rows_note(c) for c in collected]
    if collected:
        trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, collected, mode)
        trace["status"] = "ok"
    else:
        trace["status"] = "metadata_only"
        trace["answer"] = chat(model, metadata_messages(question, slim(pool[:16]), mode), 0.9 if mode == "scoop" else 0, 3000 if mode == "scoop" else 2000)
    return trace


def run_one(model: str, mode: str, question: str) -> dict:
    return gather_deep(model, question, mode) if mode in {"deep", "scoop"} else gather_fast(model, question, mode)


def main():
    ap = argparse.ArgumentParser(description="NDAP query regression test (shares prompts.json with the web app).")
    ap.add_argument("--mode", choices=["fast", "deep", "scoop"], help="Mode for --query/--homepage/--srit items (suite items carry their own).")
    ap.add_argument("--model", default="google/gemini-2.5-flash")
    ap.add_argument("--srit", type=Path, help="SRIT template markdown to parse queries from")
    ap.add_argument("--homepage", action="store_true", help="Run the 4 homepage chips")
    ap.add_argument("--query", action="append", help="Ad-hoc query (repeatable)")
    ap.add_argument("--out", type=Path, help="Where to write JSON results (default: data/batch_runs/test_queries_<ts>.json)")
    args = ap.parse_args()

    ad_hoc = bool(args.homepage or args.srit or args.query)
    # items: (label, question, mode, expect_any)
    items: list[tuple] = []
    if not ad_hoc:
        for s in SUITE:
            items.append((s["label"], s["q"], s["mode"], s.get("expect_any")))
    else:
        mode = args.mode or "deep"
        if args.homepage:
            for i, q in enumerate(HOMEPAGE_CHIPS, 1):
                items.append((f"homepage-{i}", q, mode, None))
        if args.srit:
            for i, q in enumerate(parse_srit_queries(args.srit), 1):
                items.append((f"srit-{i}", q, mode, None))
        for i, q in enumerate(args.query or [], 1):
            items.append((f"custom-{i}", q, mode, None))

    results = []
    passed = failed = 0
    for label, question, mode, expect_any in items:
        print(f"\n[{mode.upper()}] {label} …", flush=True)
        t0 = time.time()
        try:
            trace = run_one(args.model, mode, question)
            trace.update({"label": label, "question": question, "elapsed_s": round(time.time() - t0, 1)})
            if expect_any:
                ans = str(trace.get("answer") or "")
                hit = next((e for e in expect_any if e.lower() in ans.lower()), None)
                trace["check"] = {"expect_any": expect_any, "passed": bool(hit), "matched": hit}
                if hit:
                    passed += 1
                else:
                    failed += 1
                tag = "PASS" if hit else "FAIL"
                print(f"  status={trace.get('status')} datasets={trace.get('dataset_ids')} check={tag} ({trace['elapsed_s']}s)", flush=True)
            else:
                print(f"  status={trace.get('status')} datasets={trace.get('dataset_ids')} ({trace['elapsed_s']}s)", flush=True)
            results.append(trace)
        except Exception as e:
            failed += 1 if expect_any else 0
            results.append({"label": label, "question": question, "mode": mode, "status": "error", "error": str(e), "elapsed_s": round(time.time() - t0, 1)})
            print(f"  ERROR: {e}", flush=True)

    out = args.out or (ROOT / "data/batch_runs" / f"test_queries_{int(time.time())}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    checked = passed + failed
    summary = f"{passed}/{checked} checks passed" if checked else f"{len(results)} runs (no checks)"
    print(f"\nWrote {out} — {summary}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
