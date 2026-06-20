#!/usr/bin/env python3
"""Headless batch runner mirroring docs/index.html fast & deep pipelines."""
from __future__ import annotations

import argparse
import json
import re
import sys
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
MAX_LLM_ROWS = 300
MAX_PAGES = 8
PAGE_SIZE = 1000

INDEX = json.loads((DOCS / "assets/ndap_index.json").read_text())
RECIPES = json.loads((DOCS / "assets/ndap_recipes.json").read_text())

AGG_GUARDRAIL = (
    " CRITICAL aggregation rule: the supplied rows may be a PARTIAL, filtered, or TRUNCATED subset. "
    "Never compute a sum, total, count, or cross-entity average (across towns/states/categories) from a subset "
    "marked PARTIAL or TRUNCATED — that result would be wrong. Only aggregate across entities when the dataset is "
    "marked COMPLETE. If the question needs a total but the rows are partial/truncated/too granular, do not "
    "fabricate one: prefer a row that already represents the requested total (e.g. a 'Persons'/'Total'/national row), "
    "otherwise state the dataset is too granular or incomplete to total here and label it 'Low Confidence / Unverified'."
)

NDAP_HARD_RULE = (
    " HARD RULE — SOURCE: NDAP is the ONLY permitted source. Use ONLY the NDAP data/metadata supplied in this prompt. "
    "Never use outside or general knowledge, training-data facts, or any non-NDAP source, and never cite or link anything "
    "other than NDAP datasets (ndap.niti.gov.in). If the supplied NDAP data does not answer the question, say so plainly."
)

INDIA_SCOPE = (
    " SCOPE: this platform answers questions about INDIA. If a dataset spans multiple countries or many time periods, "
    "isolate India and the year(s) the question asks for (or the most recent available) — never report another country's "
    "value or an unrelated/old period as if it were the answer."
)

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
        {"role": "system", "content": "You plan searches over an NDAP metadata index. Return JSON only. Pick concise search terms plus useful synonyms. Do not answer the question."},
        {"role": "user", "content": f"Current question:\n{question}\n\nReturn exactly: {{\"search_query\":\"...\",\"reason\":\"...\"}}"},
    ]
    try:
        p = extract_json(chat(model, msgs, 0, 400))
        return str(p.get("search_query") or question), str(p.get("reason") or "")
    except Exception as e:
        return question, f"fallback: {e}"


def plan_deep(model: str, question: str):
    msgs = [
        {"role": "system", "content": "You plan a multi-step research process over an NDAP metadata index. Break the question into distinct data needs. Return JSON only. Give 1-4 concise search queries. Do not answer the question."},
        {"role": "user", "content": f"Current question:\n{question}\n\nReturn exactly: {{\"search_queries\":[\"...\"],\"sub_questions\":[\"...\"],\"reason\":\"...\"}}"},
    ]
    try:
        p = extract_json(chat(model, msgs, 0, 600))
        qs = [str(x).strip() for x in p.get("search_queries", []) if str(x).strip()] or [question]
        return qs[:4], str(p.get("reason") or "")
    except Exception as e:
        return [question], f"fallback: {e}"


def select_datasets(model: str, question: str, pool, already: list[str], n: int):
    have = f"Already downloaded: {', '.join(already)}. Pick only NEW datasets.\n" if already else ""
    grain = (
        "GEOGRAPHY: each candidate has 'grain' (its finest geographic level, e.g. Country / State / State, District) "
        "and 'dims' (its actual dimension names). A dataset can ONLY answer for a place if its grain/dims can resolve "
        "that place — a CITY question (Mumbai, Kolkata) needs a city/town/ward dimension; a STATE question needs State "
        "in grain/dims; a national total wants a Country-grain dataset. Do NOT pick a Country-grain dataset for a "
        "city/state question just because its name mentions the topic — judge by grain and dims, not the title. If NO "
        "candidate has fine-enough grain, pick the closest coarser-grain dataset so the answer can report what IS "
        "available with a caveat. Also for a national/state total, prefer a dataset already reported at that level over "
        "a highly granular one (a national total cannot be reconstructed by summing partially-downloaded sub-rows). "
        "INDIA SCOPE: this platform answers questions about India, so prefer datasets scoped to India (grain "
        "Country/State/District/etc.) over multi-country/'Global' series (e.g. ILO or World-Bank global datasets); only "
        "choose a Global-grain dataset when no India-scoped candidate covers the measure."
    )
    msgs = [
        {"role": "system", "content": f"Choose up to {n} dataset(s) to DOWNLOAD — FEWER IS BETTER. {grain} Return JSON only."},
        {"role": "user", "content": f"{have}Current question:\n{question}\n\nCandidates:\n{json.dumps(slim(pool))}\n\nReturn exactly: {{\"dataset_ids\":[<id>],\"reason\":\"...\"}}"},
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
    summ = "\n".join(f"Dataset {c['id']} ({c['name']}); rows: {len(c['used'])}" for c in collected)
    msgs = [
        {"role": "system", "content": "Judge whether gathered NDAP datasets suffice. Return JSON only."},
        {"role": "user", "content": f"Current question:\n{question}\n\nGathered:\n{summ or '(nothing)'}\n\nReturn exactly: {{\"sufficient\":true|false,\"missing\":\"...\",\"next_query\":\"...\"}}"},
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
    used = select_relevant(rows, question, row_cap)
    return {"id": pick["id"], "name": pick["name"], "columns": cols, "rows": rows, "used": used, "csv": to_csv(cols, used), "truncated": trunc}


def metadata_messages(question, candidates):
    return [
        {"role": "system", "content": "You are an NDAP-only research assistant. Answer using ONLY supplied metadata. Cite dataset IDs. Do not invent values. Use markdown only." + NDAP_HARD_RULE},
        {"role": "user", "content": f"Current question:\n{question}\n\nCandidate metadata:\n{json.dumps(candidates, indent=2)}\n\nGive a concise grounded answer."},
    ]


MAX_DRILL_ITERS = 3
DRILL_ROWS = 500
PROFILE_VALUES_CAP = 40


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


def drill_rows(c, req):
    sent = c.setdefault("_sent", list(c["used"]))
    sent_ids = {id(r) for r in sent}
    pool = c["rows"]
    where = req.get("where") if isinstance(req.get("where"), dict) else None
    if where:
        entries = [(k, v) for k, v in where.items() if k in c["columns"]]
        if entries:
            pool = [r for r in c["rows"] if all(str(v).lower() in str(cell_value(r.get(k)) if r.get(k) is not None else "").lower() for k, v in entries)]
    unseen = [r for r in pool if id(r) not in sent_ids]
    chosen = (unseen if unseen else pool)[:DRILL_ROWS]
    sent.extend(chosen)
    return chosen


def parse_fetch_request(text):
    try:
        o = extract_json(text)
        if isinstance(o, dict) and isinstance(o.get("fetch_rows"), dict):
            return o["fetch_rows"]
    except Exception:
        pass
    return None


def data_initial_messages(question, collected, deep, any_hidden):
    sys = ("You are an NDAP-only deep-research analyst across MULTIPLE datasets." if deep else "You are an NDAP-only data analyst.") + " Compute ONLY from supplied CSV rows. Cite dataset ID. Use markdown only — no LaTeX." + AGG_GUARDRAIL + INDIA_SCOPE + NDAP_HARD_RULE
    blocks = []
    for c in collected:
        hidden = len(c["used"]) < len(c["rows"])
        profile = ("\n" + dataset_profile_text(c)) if hidden else ""
        label = f"Sample rows ({len(c['used'])} most-relevant of {len(c['rows'])}{'+' if c['truncated'] else ''}, CSV):" if hidden else "All rows (CSV):"
        blocks.append(f"Dataset {c['id']} — {c['name']}\nColumns: {', '.join(c['columns'])}\n{rows_note(c)}{profile}\n\n{label}\n{c['csv']}")
    body = ("\n\n" + "=" * 40 + "\n\n").join(blocks)
    protocol = ""
    if any_hidden:
        protocol = (
            "\n\nIMPORTANT — you can pull MORE rows than the sample. If the rows you need (a national/'Persons'/'Total' row, "
            "a specific state/city, a specific year, or simply more rows) are NOT in the sample, do NOT guess and do NOT claim "
            "the data is missing — request them. When prompted, reply with ONLY this JSON:\n"
            '{"fetch_rows":{"dataset":<id>,"where":{"<column>":"<value>"},"more":false,"reason":"why"}}\n'
            f"Use the listed dimension values for filters, or set 'more':true for the next batch. Up to {MAX_DRILL_ITERS} fetches."
        )
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"Current question:\n{question}\n\n{body}{protocol}"},
    ]


def synthesize_with_drilldown(model, question, collected):
    any_hidden = any(len(c["used"]) < len(c["rows"]) for c in collected)
    messages = data_initial_messages(question, collected, deep=len(collected) > 1, any_hidden=any_hidden)
    drills = []
    if any_hidden:
        ask = "Decision: do you need additional or different rows to answer accurately? If yes, reply with ONLY the fetch_rows JSON. If the rows shown are sufficient, reply with exactly: READY"
        for _ in range(MAX_DRILL_ITERS):
            messages.append({"role": "user", "content": ask})
            resp = chat(model, messages, 0, 450)
            req = parse_fetch_request(resp)
            if not req:
                messages.pop()
                break
            messages.append({"role": "assistant", "content": resp})
            ds = next((c for c in collected if str(c["id"]) == str(req.get("dataset"))), collected[0])
            got = drill_rows(ds, req)
            drills.append({"dataset": ds["id"], "where": req.get("where"), "more": req.get("more"), "rows": len(got), "reason": req.get("reason")})
            csv = to_csv(ds["columns"], got) if got else "(no rows matched that filter)"
            messages.append({"role": "user", "content": f"Rows for dataset {ds['id']} ({len(got)}):\n{csv}"})
    answer_ask = "Now write the final grounded answer in markdown prose — actual numbers, units, year, citing each dataset by ID. Do NOT reply with JSON or a fetch_rows request; just write the answer. Use markdown only — no LaTeX."
    messages.append({"role": "user", "content": answer_ask})
    final = chat(model, messages, 0, 3000)
    stray = parse_fetch_request(final) if any_hidden else None
    if stray:
        ds = next((c for c in collected if str(c["id"]) == str(stray.get("dataset"))), collected[0])
        got = drill_rows(ds, stray)
        drills.append({"dataset": ds["id"], "where": stray.get("where"), "more": stray.get("more"), "rows": len(got), "reason": stray.get("reason"), "phase": "final"})
        csv = to_csv(ds["columns"], got) if got else "(no rows matched that filter)"
        messages.append({"role": "assistant", "content": final})
        messages.append({"role": "user", "content": f"Rows for dataset {ds['id']} ({len(got)}):\n{csv}\n\n{answer_ask}"})
        final = chat(model, messages, 0, 3000)
    return final, drills


def gather_fast(model: str, question: str) -> dict:
    trace = {"mode": "fast"}
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
        trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, [got])
        trace["status"] = "ok"
    except Exception as e:
        trace["status"] = "download_failed"
        trace["error"] = str(e)[:200]
        trace["answer"] = chat(model, metadata_messages(question, slim(candidates[:FAST_METADATA_CANDIDATES])), 0, 2000)
    return trace


def gather_deep(model: str, question: str) -> dict:
    trace = {"mode": "deep"}
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
        trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, collected)
        trace["status"] = "ok"
    else:
        trace["status"] = "metadata_only"
        trace["answer"] = chat(model, metadata_messages(question, slim(pool[:16])), 0, 2000)
    return trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fast", "deep"], required=True)
    ap.add_argument("--model", default="google/gemini-2.5-flash")
    ap.add_argument("--srit", type=Path, help="SRIT template markdown")
    ap.add_argument("--homepage", action="store_true")
    ap.add_argument("--query", action="append")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    items: list[tuple[str, str]] = []
    if args.homepage:
        for i, q in enumerate(HOMEPAGE_CHIPS, 1):
            items.append((f"homepage-{i}", q))
    if args.srit:
        for i, q in enumerate(parse_srit_queries(args.srit), 1):
            items.append((f"srit-{i}", q))
    for i, q in enumerate(args.query or [], 1):
        items.append((f"custom-{i}", q))

    results = []
    for label, question in items:
        print(f"\n[{args.mode.upper()}] {label} …", flush=True)
        t0 = time.time()
        try:
            trace = gather_deep(args.model, question) if args.mode == "deep" else gather_fast(args.model, question)
            trace["label"] = label
            trace["question"] = question
            trace["elapsed_s"] = round(time.time() - t0, 1)
            results.append(trace)
            print(f"  status={trace.get('status')} datasets={trace.get('dataset_ids')} ({trace['elapsed_s']}s)", flush=True)
        except Exception as e:
            results.append({"label": label, "question": question, "mode": args.mode, "status": "error", "error": str(e), "elapsed_s": round(time.time() - t0, 1)})
            print(f"  ERROR: {e}", flush=True)

    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote {args.out} ({len(results)} results)")


if __name__ == "__main__":
    main()
