/* FC.core — NDAP/OpenRouter primitives ported verbatim from docs/index.html.
   Standalone IIFE for the News Factcheck page: no build step, no ES modules,
   no run/abort wiring, no UI globals. Reuses the SAME localStorage keys as the
   main app so a configured OpenRouter key/proxy is shared. */
(function () {
  "use strict";

  window.FC = window.FC || {};

  /* ---------- Constants (ported from index.html) ---------- */
  const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
  const LS = { key: "ndap.or.key", model: "ndap.or.model", searchMax: "ndap.or.searchmax", deepDownloads: "ndap.or.deepdl", proxy: "ndap.proxy", history: "ndap.history", chats: "ndap.chats" };
  const DEFAULT_MODEL = "openai/gpt-5.4-nano";
  const DEFAULT_PROXY = "https://ndap-cors-proxy.ndap-deep-research-agent.workers.dev";
  const MAX_PAGES = 8;          // hard cap on openapi pages fetched per dataset
  const PAGE_SIZE = 1000;       // NDAP openapi page size

  /* ---------- Module-internal state (closure vars) ---------- */
  let ndapIndex = null;
  let ndapRecipes = null;       // lazy-loaded on first data fetch
  let ndapPrompts = null;       // single source of truth for prompts (assets/prompts.json)
  let runUsage = null;

  /* ---------- Settings (ported getters key/model/proxy) ---------- */
  const settings = {
    get key() { return localStorage.getItem(LS.key) || ""; },
    get model() { return localStorage.getItem(LS.model) || DEFAULT_MODEL; },
    get proxy() {
      const v = localStorage.getItem(LS.proxy);
      return (v === null ? DEFAULT_PROXY : v).trim().replace(/\/+$/, "");
    },
  };

  /* ---------- Index ---------- */
  async function loadIndex() {
    if (ndapIndex) return ndapIndex;
    const res = await fetch("assets/ndap_index.json");
    if (!res.ok) throw new Error(`index fetch failed: ${res.status}`);
    ndapIndex = await res.json();
    const ministries = new Set(), sectors = new Set();
    for (const item of (ndapIndex.items || [])) {
      const m = String(item.ministry || "").trim();
      const s = String(item.sector || "").trim();
      if (m) ministries.add(m);
      if (s) sectors.add(s);
    }
    ndapIndex.ministryCount = ministries.size;
    ndapIndex.sectorCount = sectors.size;
    return ndapIndex;
  }

  // Prompts live in assets/prompts.json (shared verbatim with scripts/test_queries.py).
  async function loadPrompts() {
    if (ndapPrompts) return ndapPrompts;
    const res = await fetch("assets/prompts.json");
    if (!res.ok) throw new Error(`prompts fetch failed: ${res.status}`);
    ndapPrompts = await res.json();
    return ndapPrompts;
  }
  // Resolve a prompt by key, replacing {{token}} with another prompt entry or a caller param.
  // One pass suffices because referenced entries hold no further tokens.
  function P(key, params) {
    const raw = (ndapPrompts && ndapPrompts[key]) || "";
    const map = Object.assign({}, ndapPrompts, params || {});
    return raw.replace(/\{\{(\w+)\}\}/g, (_, k) => (map[k] != null ? map[k] : ""));
  }

  function tokenize(text) {
    return (String(text || "").toLowerCase().match(/[a-z0-9]+/g) || []).filter((t) => t.length > 2);
  }
  function searchIndex(searchQuery, limit) {
    const terms = tokenize(searchQuery);
    if (!terms.length) return [];
    const scored = [];
    for (const item of ndapIndex.items) {
      const name = String(item.name).toLowerCase();
      const desc = String(item.description).toLowerCase();
      const sect = String(item.sector).toLowerCase();
      const min = String(item.ministry).toLowerCase();
      let score = 0;
      for (const t of terms) {
        if (name.includes(t)) score += 8;
        if (desc.includes(t)) score += 5;
        if (sect.includes(t)) score += 3;
        if (min.includes(t)) score += 2;
      }
      if (score) scored.push({ item, score });
    }
    scored.sort((a, b) => b.score - a.score || a.item.id - b.item.id);
    return scored.slice(0, limit).map((r) => r.item);
  }

  /* ---------- OpenRouter ---------- */
  // Per-query usage accumulator (tokens + cost across all model calls in one run).
  function accumulateUsage(u) {
    if (!u || !runUsage) return;
    runUsage.calls += 1;
    runUsage.prompt += u.prompt_tokens || 0;
    runUsage.completion += u.completion_tokens || 0;
    runUsage.reasoning += u.completion_tokens_details?.reasoning_tokens || 0;
    runUsage.total += u.total_tokens || ((u.prompt_tokens || 0) + (u.completion_tokens || 0));
    if (typeof u.cost === "number") { runUsage.cost += u.cost; runUsage.hasCost = true; }
  }

  function orHeaders() {
    return {
      "Authorization": `Bearer ${settings.key}`,
      "Content-Type": "application/json",
      "HTTP-Referer": location.origin + location.pathname,
      "X-Title": "NDAP Deep Research Agent",
    };
  }

  async function fetchWithTimeout(url, options = {}, ms = 180000) {
    const timeoutCtrl = new AbortController();
    const timer = setTimeout(() => timeoutCtrl.abort(), ms);
    try {
      return await fetch(url, { ...options, signal: timeoutCtrl.signal });
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error(`Request timed out after ${Math.round(ms / 1000)}s`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }
  async function orComplete(messages, temperature = 0.2, maxTokens = 1024) {
    const res = await fetchWithTimeout(OPENROUTER_URL, {
      method: "POST", headers: orHeaders(),
      body: JSON.stringify({ model: settings.model, messages, temperature, max_tokens: maxTokens, usage: { include: true } }),
    }, 180000);
    if (!res.ok) throw new Error(`OpenRouter ${res.status}: ${(await res.text()).slice(0, 240)}`);
    const data = await res.json();
    accumulateUsage(data.usage);
    return data.choices?.[0]?.message?.content || "";
  }
  function extractJson(text) {
    // The first "{" … last "}" slice naturally excludes any ```json fences
    // (they sit outside the braces) and tolerates prose around the object.
    const s = String(text);
    const start = s.indexOf("{");
    const end = s.lastIndexOf("}");
    if (start < 0 || end < start) throw new Error("no JSON object in model reply");
    return JSON.parse(s.slice(start, end + 1));
  }

  /* ---------- Data layer (proxy → NDAP openapi) ---------- */
  async function loadRecipes() {
    if (ndapRecipes) return ndapRecipes;
    const res = await fetch("assets/ndap_recipes.json");
    if (!res.ok) throw new Error(`recipes fetch failed: ${res.status}`);
    ndapRecipes = await res.json();
    return ndapRecipes;
  }

  function buildNdapUrl(recipe, pageno) {
    const base = (ndapRecipes && ndapRecipes.base) || "https://loadqa.ndapapi.com/v1/openapi";
    const ind = encodeURIComponent(recipe.i).replace(/%2C/g, ",");
    const dim = encodeURIComponent(recipe.d).replace(/%2C/g, ",");
    return `${base}?API_Key=${encodeURIComponent(recipe.k)}&ind=${ind}&dim=${dim}&pageno=${pageno}`;
  }

  function proxied(url) {
    return `${settings.proxy}/?url=${encodeURIComponent(url)}`;
  }

  async function fetchDatasetRows(datasetId, onProgress) {
    const recipes = await loadRecipes();
    const recipe = recipes.recipes[String(datasetId)];
    if (!recipe) throw new Error(`No download recipe for dataset ${datasetId}`);

    let columns = [];
    const rows = [];
    let truncated = false;
    for (let page = 1; page <= MAX_PAGES; page++) {
      const res = await fetchWithTimeout(proxied(buildNdapUrl(recipe, page)), {}, 90000);
      if (!res.ok) throw new Error(`proxy/NDAP ${res.status}: ${(await res.text()).slice(0, 160)}`);
      const payload = await res.json();
      if (payload.IsError) throw new Error(`NDAP error: ${payload.Message || "unknown"}`);

      if (!columns.length) {
        columns = (payload.Headers?.Items || [])
          .map((h) => String(h.ID || h.DisplayName || "").trim())
          .filter(Boolean);
      }
      const pageRows = payload.Data || [];
      for (const r of pageRows) rows.push(r);
      onProgress?.(rows.length, page);

      if (pageRows.length < PAGE_SIZE) break;
      if (page === MAX_PAGES) truncated = true;
    }
    return { columns, rows, truncated };
  }

  // NDAP indicator cells are aggregation objects ({avg,sum,min,max,count,…}); flatten to a scalar.
  function cellValue(v) {
    if (v && typeof v === "object") {
      if (v.avg != null) return v.avg;
      if (v.value != null) return v.value;
      if (v.sum != null) return v.sum;
      return "";
    }
    return v;
  }

  function selectRelevantRows(rows, question, max) {
    if (rows.length <= max) return rows;
    const terms = tokenize(question);
    const scored = rows.map((row) => {
      const blob = Object.values(row).map(cellValue).join(" ").toLowerCase();
      let s = 0;
      for (const t of terms) if (blob.includes(t)) s++;
      return { row, s };
    });
    scored.sort((a, b) => b.s - a.s);
    return scored.slice(0, max).map((x) => x.row);
  }

  function rowsToCsv(columns, rows) {
    const esc = (v) => {
      const s = String(v ?? "");
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const head = columns.join(",");
    const body = rows.map((r) => columns.map((c) => esc(cellValue(r[c]))).join(",")).join("\n");
    return `${head}\n${body}`;
  }

  /* ---------- Dataset selection (history-free) ---------- */
  // "grain" is the dataset's true finest geographic level; "dims" are its real dimension
  // names. These are reliable, unlike the legacy geo field (which mislabels non-geographic
  // dimensions as city). The selector matches the question's geography against these.
  const slimCandidates = (list) => list.map((c) => ({ id: c.id, name: c.name, grain: c.grain || "", dims: c.dims || [], years: c.years, about: c.description }));

  // Pick up to n NEW datasets to download that together cover the statement (n=1 ⇒ fast mode).
  async function selectDatasets(statement, pool, alreadyHave, n) {
    const have = alreadyHave.length ? `Already downloaded: ${alreadyHave.join(", ")}. Pick only NEW datasets that add information still missing.\n` : "";
    const messages = [
      { role: "system", content: P("select_datasets_sys", { n }) },
      { role: "user", content: `${""}${have}Current question:\n${statement}\n\nCandidates:\n${JSON.stringify(slimCandidates(pool))}\n\nReturn exactly: {"dataset_ids":[<id>, ...],"reason":"..."}` },
    ];
    const fresh = (c) => !alreadyHave.includes(String(c.id));
    try {
      const p = extractJson(await orComplete(messages, 0));
      const ids = (Array.isArray(p.dataset_ids) ? p.dataset_ids : []).map(String);
      const picks = [];
      for (const id of ids) {
        const m = pool.find((c) => String(c.id) === id);
        if (m && !picks.includes(m) && fresh(m)) picks.push(m);
      }
      if (!picks.length) { const firstNew = pool.find(fresh); if (firstNew) picks.push(firstNew); }
      return { picks: picks.slice(0, n), reason: String(p.reason || "Top-ranked candidates.") };
    } catch (_) {
      return { picks: pool.filter(fresh).slice(0, n), reason: "Fallback: top-ranked candidates." };
    }
  }

  /* ---------- Readiness ---------- */
  function ready() { return !!(ndapIndex && ndapPrompts); }

  /* ---------- Public API ---------- */
  FC.core = {
    settings,
    loadIndex,
    loadRecipes,
    loadPrompts,
    ready,
    P,
    searchIndex,
    orComplete,
    extractJson,
    selectDatasets,
    fetchDatasetRows,
    selectRelevantRows,
    rowsToCsv,
  };
})();
