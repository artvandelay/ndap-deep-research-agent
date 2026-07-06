# Executor Plan: Scoop Mode (v-next)

> **Branch target:** implement on `v-next-scoop-mode` (or a child branch). This document is the single source of truth for the Sonnet-class executor. Do not refactor outside the listed edits.

## Goal

Add a third research mode **`scoop`** to the NDAP browser chat (`docs/index.html`) and headless test runner (`scripts/test_queries.py`). Scoop reuses the **Fast** evidence pipeline unchanged (plan → search → pick one dataset → download → agentic row drilldown) but synthesizes answers in a **journalistic, opinionated, truth-grounded voice**: punchy H3 headline, one-line lede, story told through cited NDAP numbers, a **"The Take"** section with labeled *Opinion* / *Forecast* items derived from cited rows, and a one-line disclaimer. Synthesis uses temperature **0.9**, max output **2200** tokens, and the Fast wall-clock deadline (**120 s**). Fast and Deep modes must remain behavior-identical after the change.

## Constraints for the executor

- Make only the changes specified in this stream. Do not refactor adjacent code.
- Do not invent file paths, package names, or APIs. If a referenced symbol is missing, stop and report.
- Match existing code style in the touched files (indent, quotes, import order).
- After your edits, run the project's typecheck/lint/test commands listed in the stream and report exact output.
- If acceptance criteria cannot be met as written, stop and report what's blocking — do not improvise.
- Do not modify dependency manifests unless the stream explicitly tells you to.
- Do not delete or rename files unless the stream explicitly tells you to.

---

## Stream 0: Contract (read-only — do not edit in parallel streams)

**Frozen mode string:** `"scoop"` (internal); UI label `"Scoop"`.

**Valid chat modes:** `"fast" | "deep" | "scoop"`.

**New prompt keys in `docs/assets/prompts.json`:**

| Key | Purpose |
|-----|---------|
| `scoop_style` | Voice, structure, Opinion/Forecast labeling, disclaimer; includes `{{ndap_hard_rule}}` |
| `scoop_sys_single` | System prompt for data path (single dataset) |
| `scoop_metadata_sys` | System prompt for metadata-only fallback (no proxy) |
| `scoop_answer_ask` | Final synthesis user message (replaces `answer_ask` in scoop runs) |

**Changed function signatures (both files must match):**

```javascript
// docs/index.html
function normalizeMode(mode) { /* returns "fast" | "deep" | "scoop" */ }
function chatMode() { /* returns normalizeMode(currentChat()?.mode) */ }
function setChatMode(mode) { /* persists normalizeMode(mode) */ }
function modeLabel(mode) { /* "Fast" | "Deep" | "Scoop" */ }
function metadataMessages(question, candidates, histPreamble, mode = "fast")
function dataInitialMessages(question, collected, histPreamble, mode = "fast")
async function synthesizeWithDrilldown(question, collected, history, ui, mode, onDelta, maxOut)
// run() routes: deep → gatherDeep; fast OR scoop → gatherFast
// scoop synthesis: temperature 0.9, maxOut 2200, scoop_answer_ask
```

```python
# scripts/test_queries.py
def metadata_messages(question, candidates, mode="fast")
def data_initial_messages(question, collected, mode="fast")
def synthesize_with_drilldown(model, question, collected, mode="fast")
def gather_scoop(model, question)  # alias: gather_fast + scoop synthesis params
def run_one(model, mode, question)  # accepts "scoop"
```

**Scoop runtime constants (add near existing deadline constants in `index.html`):**

```javascript
const SCOOP_TEMPERATURE = 0.9;
const SCOOP_MAX_OUT = 2200;
```

**CSS accent for active Scoop toggle:** `#e85d04` (warm orange).

---

## Work streams (parallel)

### Stream A: Prompts

- **Files:** [docs/assets/prompts.json](docs/assets/prompts.json)
- **Depends on:** Stream 0
- **Do not touch:** any other file

**Subagent prompt:**

```
You are implementing Stream A: Prompts of the Scoop mode plan.
Other streams are running in parallel — do not touch files outside your list.

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: docs/assets/prompts.json
Files you may read for context: docs/assets/prompts.json

Interface contract (frozen, do not change):
Add exactly four new keys after the existing "answer_ask" entry (before the closing `}`).
Do not modify any existing keys.

Tasks (do in order):
1. Open docs/assets/prompts.json.
2. After the "answer_ask" line, add a comma and paste the four keys below EXACTLY (valid JSON).

Verification (run these and paste output in your final report):
- python3 -c "import json; d=json.load(open('docs/assets/prompts.json')); assert all(k in d for k in ['scoop_style','scoop_sys_single','scoop_metadata_sys','scoop_answer_ask']); print('OK', len(d), 'keys')"

Acceptance criteria (all must be true before reporting done):
- JSON parses without error
- All four new keys exist with non-empty string values
- Existing keys unchanged

If anything is ambiguous or a referenced symbol is missing, STOP and report — do not guess.
```

**Paste these four keys (exact text):**

```json
  "scoop_style": " SCOOP MODE — VOICE: You are a sharp data journalist writing for a general audience about India's public statistics. Write with energy and narrative flair — punchy headlines, vivid but accurate framing, short paragraphs. Sensational framing is allowed ONLY when the cited numbers support it (e.g. \"Mumbai's slum count jumped 42% between censuses — and the data saw it coming\"). NEVER invent numbers, years, places, or trends not present in the supplied NDAP rows/metadata. STRUCTURE (markdown, in this order): (1) `###` headline — one compelling line; (2) **Lede** — one sentence hook grounded in the key figure; (3) **The Numbers** — the facts: show exact figures in a small markdown table or bullet list with units and year; cite each dataset by ID as a clickable markdown link to https://ndap.niti.gov.in/dataset/<DATASET_ID>; (4) **The Take** — 1–3 items mixing interpretation; each item MUST start with *Opinion:* or *Forecast:*; opinions interpret what the cited numbers imply today; forecasts extrapolate ONLY from cited trend(s) between observed years and MUST state the basis (e.g. \"*Forecast:* If the 2001→2011 growth rate held…\"); no causal claims unless the data directly compares over time; (5) one-line italic disclaimer: _Scoop mode: editorial voice, NDAP-sourced figures only — verify before citing._ Reply in the user's language. {{markdown_latex}}{{india_scope}}{{ndap_hard_rule}}{{agg_guardrail}}",

  "scoop_sys_single": "You are an NDAP-only data journalist for India's National Data and Analytics Platform. Compute every figure ONLY from the supplied CSV rows of one NDAP dataset; use prior conversation only to interpret the question. SCOOP MODE — VOICE: You are a sharp data journalist writing for a general audience about India's public statistics. Write with energy and narrative flair — punchy headlines, vivid but accurate framing, short paragraphs. Sensational framing is allowed ONLY when the cited numbers support it. NEVER invent numbers, years, places, or trends not present in the supplied NDAP rows. STRUCTURE (markdown, in this order): (1) `###` headline; (2) **Lede** — one sentence hook grounded in the key figure; (3) **The Numbers** — exact figures with units/year, cite dataset by ID as markdown link to https://ndap.niti.gov.in/dataset/<DATASET_ID>; (4) **The Take** — 1–3 items, each starting with *Opinion:* or *Forecast:*; forecasts extrapolate ONLY from cited trends and MUST state the basis; (5) italic disclaimer: _Scoop mode: editorial voice, NDAP-sourced figures only — verify before citing._ Cite the dataset by its ID. Show the exact numbers you used. Do not invent values absent from the rows. If a requested entity is missing from the rows, say so in The Numbers and skip speculative Take items. Reply in the user's language. {{markdown_latex}}{{india_scope}}{{ndap_hard_rule}}{{agg_guardrail}}",

  "scoop_metadata_sys": "You are an NDAP-only data journalist for India's National Data and Analytics Platform. Answer using ONLY the supplied NDAP metadata; use prior conversation only to interpret the question. SCOOP MODE — VOICE: You are a sharp data journalist writing for a general audience about India's public statistics. Write with energy and narrative flair — punchy headlines, vivid but accurate framing, short paragraphs. Sensational framing is allowed ONLY when the metadata supports it. NEVER invent raw values. STRUCTURE (markdown, in this order): (1) `###` headline; (2) **Lede**; (3) **The Numbers** — describe what metadata shows without inventing values, cite datasets by ID as markdown links; (4) **The Take** — labeled *Opinion:* / *Forecast:* items tied to metadata; (5) italic disclaimer: _Scoop mode: editorial voice, NDAP-sourced figures only — verify before citing._ If metadata is insufficient, say so instead of guessing. Reply in the user's language. {{markdown_latex}}{{india_scope}}{{ndap_hard_rule}}",

  "scoop_answer_ask": "Now write the final Scoop answer in markdown following the Scoop structure (headline, Lede, The Numbers, The Take, disclaimer). Use actual numbers from the evidence above, cite each dataset by ID, and label every Take item as *Opinion:* or *Forecast:*. Do NOT reply with JSON or a tool request; just write the answer."
```

---

### Stream B: HTML + CSS

- **Files:** [docs/index.html](docs/index.html) — **regions only:** `<style>` block lines ~122–136, welcome `info-block` modes ~544–553, `#modeToggle` ~580–589, composer hint ~599
- **Depends on:** Stream 0
- **Do not touch:** `<script>` block

**Subagent prompt:**

```
You are implementing Stream B: HTML + CSS of the Scoop mode plan.
Other streams are running in parallel — do not edit the <script> block or docs/assets/prompts.json.

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: docs/index.html (HTML + CSS regions only)
Files you may read for context: docs/index.html

Tasks (do in order):

1. CSS (~line 135): After this existing rule:
    .mode-toggle button[data-mode="deep"].active { color: var(--blue); }
   Add:
    .mode-toggle button[data-mode="scoop"].active { color: #e85d04; }

2. Welcome info-block (~line 549): After the Deep mode-line closing </div>, add:
              <div class="mode-line">
                <span class="mode-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.5-1.5-3-3-3s-3 1.5-3 3 1.5 3 3 3z"/><path d="M12 2c1 3 2 5 2 8a6 6 0 0 1-12 0c0-3 1-5 2-8"/><path d="M8.5 16.5 6 22h12l-2.5-5.5"/></svg></span>
                <span><strong>Scoop</strong> tells the story behind the numbers — journalistic voice, labeled opinions and forecasts, still NDAP-grounded.</span>
              </div>

3. Mode toggle (~line 587): After the Deep button closing </button>, add:
          <button type="button" data-mode="scoop">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.5-1.5-3-3-3s-3 1.5-3 3 1.5 3 3 3z"/><path d="M12 2c1 3 2 5 2 8a6 6 0 0 1-12 0c0-3 1-5 2-8"/><path d="M8.5 16.5 6 22h12l-2.5-5.5"/></svg>
            Scoop
          </button>

4. Composer hint (~line 599): Replace:
    Switch Fast/Deep anytime before sending
   With:
    Switch Fast / Deep / Scoop anytime before sending

Verification:
- grep -n 'data-mode="scoop"' docs/index.html | head -3
- grep -n 'Scoop' docs/index.html | head -8

Acceptance criteria:
- Third toggle button present with data-mode="scoop" and label "Scoop"
- CSS rule for [data-mode="scoop"].active exists
- Welcome info-block mentions Scoop
- Composer hint mentions all three modes
- No edits inside <script>
```

---

### Stream C: Script — mode plumbing + synthesis

- **Files:** [docs/index.html](docs/index.html) — **`<script>` block only**
- **Depends on:** Stream 0 (prompt key names); reads Stream A output at integration if running strictly sequential — otherwise assume keys exist per contract
- **Do not touch:** HTML/CSS outside `<script>`

**Subagent prompt:**

```
You are implementing Stream C: Script mode plumbing of the Scoop mode plan.
Other streams are running in parallel — edit only the <script> block in docs/index.html.

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: docs/index.html (<script> only)
Files you may read: docs/assets/prompts.json, docs/index.html

Interface contract: see Stream 0 in docs/plans/v-next-scoop-mode.md

Tasks (do in order):

1. Add constants after RUN_DEADLINE_DEEP_MS (~line 685):
    const SCOOP_TEMPERATURE = 0.9;
    const SCOOP_MAX_OUT = 2200;

2. Add helper before chatMode() (~line 1498):
    function normalizeMode(mode) {
      const m = String(mode || "fast").toLowerCase();
      return m === "deep" || m === "scoop" ? m : "fast";
    }

3. Replace chatMode (~line 1499):
    // OLD: function chatMode() { const c = currentChat(); return c && c.mode === "deep" ? "deep" : "fast"; }
    // NEW:
    function chatMode() {
      const c = currentChat();
      return normalizeMode(c && c.mode);
    }

4. Replace setChatMode (~line 1500-1505):
    function setChatMode(mode) {
      const c = currentChat();
      if (!c || busy) return;
      c.mode = normalizeMode(mode);
      saveChats();
      renderModeToggle();
    }

5. Replace rememberTurn turnMode (~line 1477):
    // OLD: const turnMode = mode === "deep" ? "deep" : "fast";
    // NEW:
    const turnMode = normalizeMode(mode);

6. Replace modeLabel (~line 1661-1663):
    function modeLabel(mode) {
      const m = normalizeMode(mode);
      if (m === "deep") return "Deep";
      if (m === "scoop") return "Scoop";
      return "Fast";
    }

7. Replace metadataMessages signature and system prompt (~line 2142):
    function metadataMessages(question, candidates, histPreamble, mode = "fast") {
      const sysKey = normalizeMode(mode) === "scoop" ? "scoop_metadata_sys" : "metadata_sys";
      return [
        { role: "system", content: P(sysKey) },
        { role: "user", content: `${histPreamble}Current question:\n${question}\n\nRetrieved candidate metadata (JSON):\n${JSON.stringify(candidates, null, 2)}\n\nGive a concise, grounded answer: likely dataset(s), why they match, and the next action.` },
      ];
    }

8. Replace dataInitialMessages (~line 2151):
    function dataInitialMessages(question, collected, histPreamble, mode = "fast") {
      const m = normalizeMode(mode);
      let sys;
      if (m === "scoop") sys = P("scoop_sys_single");
      else if (m === "deep") sys = P("data_sys_multi");
      else sys = P("data_sys_single");
      // ... keep rest of function body identical (blocks, protocol, return)

9. Replace synthesizeWithDrilldown signature and synthesis tail (~line 2246):
    async function synthesizeWithDrilldown(question, collected, history, ui, mode, onDelta, maxOut) {
      const messages = dataInitialMessages(question, collected, convoBlock(history), mode);
      // ... agent loop unchanged (still temperature 0 via orComplete) ...
      const m = normalizeMode(mode);
      const ANSWER_ASK = m === "scoop" ? P("scoop_answer_ask") : P("answer_ask");
      const synthTemp = m === "scoop" ? SCOOP_TEMPERATURE : 0;
      const answer = () => streamOrComplete(messages, synthTemp, onDelta, maxOut);
      // ... rest unchanged, use ANSWER_ASK in stray-retry loop too

10. Update gatherFast metadata fallback call (~line 2344):
    return { messages: metadataMessages(question, candidates.slice(0, FAST_METADATA_CANDIDATES), pre, "fast"), usedDataset: "" };
    (no change needed — explicit "fast" is correct)

11. Update gatherDeep metaFallback (~line 2363):
    const metaFallback = () => ({ messages: metadataMessages(question, pool.slice(0, Math.max(FAST_METADATA_CANDIDATES, 16)), pre, "deep"), usedDataset: "" });
    (pass "deep" explicitly)

12. Replace run() mode routing (~line 2447-2496):
    const modeUsed = chatMode();
    const deep = modeUsed === "deep";
    const scoop = modeUsed === "scoop";
    const deadlineMs = deep ? RUN_DEADLINE_DEEP_MS : RUN_DEADLINE_FAST_MS;
    // ...
    ui.procMeta.textContent = deep ? "deep research…" : (scoop ? "scoop…" : "working…");
    // ...
    const result = deep
      ? await gatherDeep(question, history, ui)
      : await gatherFast(question, history, ui);
    // ...
    const maxOut = deep ? 2800 : (scoop ? SCOOP_MAX_OUT : 1800);
    // ...
    const synthLabel = deep ? "synthesizing across sources…" : (scoop ? "writing the scoop…" : "streaming grounded answer…");
    const synthStep = liveStep(ui, "synthesize_answer", synthLabel, { state: "run" });
    // ...
    if (result.collected) {
      finalText = await synthesizeWithDrilldown(question, result.collected, history, ui, modeUsed, onDelta, maxOut);
    } else {
      const metaTemp = scoop ? SCOOP_TEMPERATURE : 0;
      finalText = await streamOrComplete(result.messages, metaTemp, onDelta, maxOut);
    }

13. Update stopped-run hint (~line 2516) — optional copy tweak:
    ? `Stopped after ${limitSec}s (time limit) — try Fast or Scoop mode or a narrower question.`

Verification:
- node --check <(sed -n '/<script>/,/<\/script>/p' docs/index.html | sed '1d;$d') 2>&1 || python3 -c "
import re
s=open('docs/index.html').read()
m=re.search(r'<script>(.*)</script>', s, re.S)
open('/tmp/ndap.js','w').write(m.group(1))
" && node --check /tmp/ndap.js
- grep -n 'normalizeMode\|SCOOOP_TEMPERATURE\|scoop_answer_ask\|modeUsed' docs/index.html

Acceptance criteria:
- normalizeMode exists; chatMode/setChatMode/rememberTurn/modeLabel use it
- synthesizeWithDrilldown takes `mode` not `deep`; uses scoop prompts/temp when mode==="scoop"
- run() routes scoop through gatherFast; metadata-only scoop uses temp 0.9
- gatherDeep and gatherFast behavior for fast/deep unchanged
```

---

### Stream D: README docs

- **Files:** [README.md](README.md), [docs/README.md](docs/README.md)
- **Depends on:** Stream 0

**Subagent prompt:**

```
You are implementing Stream D: README docs for Scoop mode.
Do not touch docs/index.html or prompts.json.

Tasks:

1. README.md (~line 18): Change "Fast / Deep toggle" to "Fast / Deep / Scoop toggle".
2. README.md (~line 20): After the Deep bullet, add:
   - **Scoop**: same quick pipeline as Fast, but answers in a journalistic voice — headline, lede, cited numbers, and a labeled "The Take" section for opinions and forecasts grounded in the cited NDAP rows.
3. docs/README.md (~line 15): Change "Fast / Deep modes" to "Fast / Deep / Scoop modes".
4. docs/README.md (~line 29): After the Deep deadline sentence, add:
   Scoop runs use the Fast pipeline and the 2-minute ceiling.

Verification:
- grep -n 'Scoop' README.md docs/README.md

Acceptance criteria:
- Both README files mention Scoop mode with accurate one-line description
- Fast and Deep descriptions unchanged aside from toggle wording
```

---

### Stream E: test_queries.py

- **Files:** [scripts/test_queries.py](scripts/test_queries.py)
- **Depends on:** Stream 0

**Subagent prompt:**

```
You are implementing Stream E: test_queries.py scoop support.
Do not touch docs/index.html.

Tasks:

1. Add constants after existing mode tuning (~line 60 area):
    SCOOP_TEMPERATURE = 0.9
    SCOOP_MAX_OUT = 2200

2. Add helper near top of gather functions:
    def normalize_mode(mode: str) -> str:
        m = (mode or "fast").lower()
        return m if m in {"fast", "deep", "scoop"} else "fast"

3. Change metadata_messages to accept mode and pick sys key:
    def metadata_messages(question, candidates, mode="fast"):
        sys_key = "scoop_metadata_sys" if normalize_mode(mode) == "scoop" else "metadata_sys"
        return [{"role": "system", "content": P(sys_key)}, ...]

4. Change data_initial_messages(question, collected, mode="fast"):
    m = normalize_mode(mode)
    if m == "scoop": sys = P("scoop_sys_single")
    elif m == "deep": sys = P("data_sys_multi")
    else: sys = P("data_sys_single")

5. Change synthesize_with_drilldown(model, question, collected, mode="fast"):
    messages = data_initial_messages(question, collected, mode)
    # agent loop unchanged
    answer_ask = P("scoop_answer_ask") if normalize_mode(mode) == "scoop" else P("answer_ask")
    synth_temp = SCOOP_TEMPERATURE if normalize_mode(mode) == "scoop" else 0
    max_out = SCOOP_MAX_OUT if normalize_mode(mode) == "scoop" else 3000
    messages.append({"role": "user", "content": answer_ask})
    final = chat(model, messages, synth_temp, max_out)
    # stray retry loop: same temp and answer_ask

6. Update gather_fast calls:
    synthesize_with_drilldown(model, question, [got], mode="fast")
    metadata path: metadata_messages(..., mode="fast")

7. Update gather_deep calls:
    synthesize_with_drilldown(model, question, collected, mode="deep")

8. Add gather_scoop (copy gather_fast, pass mode="scoop" to synthesize and metadata):
    def gather_scoop(model, question):
        trace = gather_fast(model, question)  # WRONG — must duplicate gather_fast body OR refactor minimally:
        # Preferred: extract shared body; minimal approach: duplicate gather_fast and replace mode strings with "scoop" and synth temp/max.

    Minimal acceptable approach — change run_one:
    def run_one(model, mode, question):
        m = normalize_mode(mode)
        if m == "deep":
            return gather_deep(model, question)
        trace = gather_fast(model, question)
        if m == "scoop" and trace.get("dataset_ids"):
            # re-synthesize with scoop if fast already computed — TOO SLOW
        # BETTER: add optional mode param to gather_fast(model, question, mode="fast")

9. Refactor gather_fast signature:
    def gather_fast(model: str, question: str, mode: str = "fast") -> dict:
        trace = {"mode": normalize_mode(mode)}
        ...
        trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, [got], mode=mode)
        ...
        trace["answer"] = chat(model, metadata_messages(question, slim(candidates[:FAST_METADATA_CANDIDATES]), mode=mode), SCOOP_TEMPERATURE if normalize_mode(mode)=="scoop" else 0, SCOOP_MAX_OUT if normalize_mode(mode)=="scoop" else 2000)

10. run_one:
    def run_one(model: str, mode: str, question: str) -> dict:
        return gather_deep(model, question) if normalize_mode(mode) == "deep" else gather_fast(model, question, mode=mode)

11. argparse (~line 665):
    ap.add_argument("--mode", choices=["fast", "deep", "scoop"], ...)

Verification:
- python3 -m py_compile scripts/test_queries.py
- python3 scripts/test_queries.py --help | grep scoop

Acceptance criteria:
- --mode scoop accepted
- gather_fast(..., mode="scoop") uses scoop prompts and temperature 0.9
- gather_deep unchanged
- Script compiles
```

---

## Integration step (sequential, single executor)

- **Trigger:** Streams A, B, C, D, E all reported success
- **Files touched:** all five files above

**Tasks:**

1. Merge/reconcile if parallel streams conflicted on `docs/index.html` — HTML/CSS (Stream B) and `<script>` (Stream C) must coexist in one file with no duplicate symbols.
2. Confirm `P("scoop_sys_single")` resolves (prompt inliner must expand `{{scoop_style}}` nested reference — verify the existing `P()` function recursively inlines keys; if not, inline `scoop_style` text directly into `scoop_sys_single` / `scoop_metadata_sys` instead of using `{{scoop_style}}` token).
3. Run full verification commands below.
4. **Rollback:** `git checkout -- .` on the feature branch or delete branch.

**Prompt inliner note:** `P()` in `docs/index.html` does a **single-pass** `{{key}}` replace (line ~1270). Do **not** nest tokens (e.g. `{{scoop_style}}` inside another prompt). The plan's `scoop_sys_single` and `scoop_metadata_sys` already inline the voice rules with top-level `{{ndap_hard_rule}}` etc. The standalone `scoop_style` key is for reference/editing only — not referenced via `{{scoop_style}}`.

---

## Verification step

Run from repo root with `OPENROUTER_API_KEY` set in environment (or `.env` loaded by your shell):

```bash
# 1. JSON validity
python3 -c "import json; json.load(open('docs/assets/prompts.json')); print('prompts OK')"

# 2. JS syntax
python3 -c "
import re
s=open('docs/index.html').read()
js=re.search(r'<script>(.*)</script>', s, re.S).group(1)
open('/tmp/ndap-check.js','w').write(js)
"
node --check /tmp/ndap-check.js && echo "JS OK"

# 3. Python syntax
python3 -m py_compile scripts/test_queries.py && echo "py OK"

# 4. Static grep checks
grep -c 'data-mode=\"scoop\"' docs/index.html   # expect >= 1
grep -c 'normalizeMode' docs/index.html         # expect >= 5
grep 'choices=\[\"fast\", \"deep\", \"scoop\"\]' scripts/test_queries.py

# 5. Headless scoop run (requires API key + network)
python3 scripts/test_queries.py --mode scoop --query "What was India's total slum population in 2011?"

# 6. Browser smoke (manual or automated)
cd docs && python3 -m http.server 8765
# Open http://localhost:8765 — toggle Scoop, ask a question, confirm:
#   - answer has ### headline, **The Take**, *Opinion:* or *Forecast:*, italic disclaimer
#   - mode badge shows "Scoop"
#   - Fast and Deep still work
```

**Pass conditions:**

| Check | Expected |
|-------|----------|
| Three-mode toggle | Fast, Deep, Scoop buttons; active state persists per chat in localStorage |
| Scoop pipeline | Same agent trace steps as Fast (plan_search → … → synthesize_answer) |
| Scoop voice | Answer contains `###`, `The Take`, `*Opinion:*` or `*Forecast:*`, and `_Scoop mode:` disclaimer |
| Grounding | Answer cites at least one `ndap.niti.gov.in/dataset/` link |
| Fast unchanged | Fast answer has no "The Take" section; temperature 0 |
| Deep unchanged | Multi-dataset reflect loop still runs |
| Export | Exported JSON/HTML includes `mode: "scoop"` for scoop turns |
| Stop/deadline | Scoop respects 120 s ceiling and Stop button |

---

## Branch workflow (for the executor after implementation)

```bash
git checkout -b v-next-scoop-mode    # or continue on existing branch
git add docs/assets/prompts.json docs/index.html README.md docs/README.md scripts/test_queries.py
git commit -m "Add Scoop mode: journalistic voice on Fast pipeline"
git push -u origin v-next-scoop-mode
```

Do **not** merge to `main` until verification passes.
