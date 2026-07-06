# v-next: "Scoop" mode — executor implementation plan

This plan is written for a weaker executor model (Sonnet-class) running as one or more subagents. Every edit below is mechanical: exact files, exact seams (2–4 lines of surrounding code quoted), and pre-written text to paste. Do not author prompt prose, pick names, or make design decisions — everything is decided here.

## Goal

Add a third per-chat answer mode, `scoop`, to the NDAP Deep Research Agent, alongside the existing `fast` and `deep` modes. Scoop is a data-journalist mode: the answer opens with an H3 headline and a bold one-line lede, tells the story through real NDAP numbers, adds a "The Take" section whose bullets are labeled **Opinion:** or **Forecast:** and derived only from cited rows, and closes with a fixed one-line disclaimer. Scoop reuses the existing `gatherFast` evidence pipeline unchanged (one search → one dataset → download → agentic row drilldown) and the Fast 120-second deadline; only synthesis changes: new prompt keys (`scoop_style`, `scoop_sys_single`, `scoop_metadata_sys`, `scoop_answer_ask`), final-answer temperature 0.9 (tool-selection calls stay at temperature 0), and max output 2200 tokens. "Done" means: the web app (`docs/index.html`) shows a three-button Fast / Deep / Scoop toggle (Scoop has a flame icon and an orange active state), a Scoop run produces the journalistic format grounded in downloaded rows, the mode is remembered per turn and shown in the per-answer mode badge, `scripts/test_queries.py --mode scoop` runs the same pipeline headless, and both READMEs mention the third mode.

## Constraints for the executor

- Make only the changes specified in this stream. Do not refactor adjacent code.
- Do not invent file paths, package names, or APIs. If a referenced symbol is missing, stop and report.
- Match existing code style in the touched files (indent, quotes, import order). `docs/index.html` uses 2-space indent and double quotes in JS; `scripts/test_queries.py` uses 4-space indent and double quotes.
- After your edits, run the verification commands listed in your stream and report exact output.
- If acceptance criteria cannot be met as written, stop and report what's blocking — do not improvise.
- Do not modify dependency manifests (`pyproject.toml`, etc.).
- Do not delete or rename files.
- Line numbers given below are anchors from the commit this plan was written against; they may drift a few lines. ALWAYS locate an edit by the quoted seam text, never by line number alone.
- Paste all prompt text, SVG markup, and README prose EXACTLY as written in this plan. Do not reword it.

## Work streams (parallel)

`docs/index.html` is one file, so Streams B and C carve it into two non-overlapping regions:

- **Stream B owns** everything BEFORE the line `  <script>` (currently line 656): the `<style>` block and the HTML body markup.
- **Stream C owns** everything INSIDE the inline `<script>…</script>` block (currently lines 656–2604).

No other pair of streams shares a file. Streams A, D, E each own their files exclusively.

### Stream 0: contract (read-only — no edits, definitions only)

- Files: none. Every other stream conforms to this section.
- Depends on: none.

**Frozen mode string.** The internal mode value is exactly `"scoop"` (lowercase). The full mode set is `"fast" | "deep" | "scoop"`. Display label: `Scoop`.

**Frozen prompt key names** (added to `docs/assets/prompts.json` by Stream A; consumed by Streams C and E):

1. `scoop_style` — voice/format rules. MUST NOT contain any `{{token}}` references. Rationale: the `P()` resolver in both `docs/index.html` (~line 1267) and `scripts/test_queries.py` (~line 59) is single-pass ("One pass suffices because referenced entries hold no further tokens"), so a key that is itself inlined via `{{scoop_style}}` must be token-free or nested tokens would survive unresolved.
2. `scoop_sys_single` — system prompt for the scoop data path (rows downloaded). References `{{scoop_style}}{{markdown_latex}}{{india_scope}}{{ndap_hard_rule}}{{agg_guardrail}}` at top level.
3. `scoop_metadata_sys` — system prompt for the scoop metadata-only fallback (no proxy configured, or the dataset download failed). References `{{scoop_style}}{{markdown_latex}}{{ndap_hard_rule}}`.
4. `scoop_answer_ask` — the final "now write the answer" user message; replaces `answer_ask` in scoop runs only.

**Frozen signature changes** (implemented by Stream C in `docs/index.html` and Stream E in `scripts/test_queries.py`):

```js
// docs/index.html — 'deep' boolean parameters widen to a 3-value mode string
function metadataMessages(question, candidates, histPreamble, mode)      // mode optional; undefined → "metadata_sys"
function dataInitialMessages(question, collected, histPreamble, mode)    // "deep" → data_sys_multi, "scoop" → scoop_sys_single, else data_sys_single
async function synthesizeWithDrilldown(question, collected, history, ui, mode, onDelta, maxOut)
async function gatherFast(question, history, ui, mode = "fast")
```

```python
# scripts/test_queries.py
def metadata_messages(question, candidates, mode="fast")
def data_initial_messages(question, collected, mode)
def synthesize_with_drilldown(model, question, collected, mode)
def gather_fast(model: str, question: str, mode: str = "fast") -> dict
```

**Frozen numeric decisions:**

- Final-answer temperature: `0.9` when mode is `"scoop"`, `0` otherwise. The agentic tool-selection calls (`orComplete(messages, 0, 700)` in the browser, `chat(model, messages, 0, 700)` in Python) stay at temperature `0` in ALL modes — do not touch them.
- Browser max output tokens (`maxOut` in `run()`): deep `2800`, scoop `2200`, fast `1800`.
- Python final-answer `max_tokens`: `2200` for scoop, `3000` otherwise (matching current behavior).
- Run deadline: scoop uses `RUN_DEADLINE_FAST_MS` (120000 ms). This falls out automatically from `const deep = modeUsed === "deep"` in `run()` — no deadline code changes.
- Scoop active-button accent color: `#e8590c` (flame orange), hardcoded in CSS like the existing one-off `#e8a33d`.

**Things that already work and MUST NOT be edited** (mode strings flow through them untouched): `resolveTurnMode` (~line 775, returns the stored string with `"fast"` fallback), `agentWho`/`.mode-badge` rendering (~line 1665, uses `modeLabel`), `addAssistant(mode)` (~line 2097), `renderModeToggle` (~line 1507, iterates all toggle buttons), `setBusy` (~line 2424, disables all toggle buttons), the `#modeToggle` click wiring (~line 2570, binds every button), export provenance (`modesUsed`, ~line 785), `newChatObject`/`loadChats` `"fast"` defaults, and `gatherDeep` (its `metaFallback` calls `metadataMessages` with no 4th argument, which resolves to `metadata_sys` — correct).

### Stream A: prompt entries in prompts.json

- Files: `docs/assets/prompts.json`
- Depends on: Stream 0 (definitions only — can start immediately)
- Subagent prompt:

```
You are implementing Stream A: prompts.json entries of a larger plan.
Other streams are running in parallel — do not touch files outside your list.

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: docs/assets/prompts.json
Files you may read for context: docs/assets/prompts.json only.

Interface contract (frozen, do not change): add exactly four keys named
scoop_style, scoop_sys_single, scoop_metadata_sys, scoop_answer_ask.
scoop_style must contain no {{token}} references (the P() resolver is single-pass).

Tasks (do in order):

1. In docs/assets/prompts.json, locate the current final entry — the file ends with:

  "answer_ask": "Now write the final grounded answer in markdown prose — actual numbers, units, year, and cite each dataset by ID. Do NOT reply with JSON or a fetch_rows request; just write the answer. Use markdown; write any formula as LaTeX in $…$ or $$…$$."
}

2. Add a comma after the "answer_ask" entry's closing quote, then insert the
   following four entries (paste EXACTLY, preserving the leading space inside
   scoop_style's value — it matches the style of ndap_hard_rule/india_scope)
   before the final closing brace, followed by a newline and the `}`:

  "scoop_style": " SCOOP VOICE: you write like a sharp data journalist filing a feature story. Structure the answer exactly like this: (1) open with a markdown H3 headline (a line starting with '### ') that captures the single most striking finding; (2) follow with a one-line lede in bold; (3) tell the story through the numbers in short, punchy paragraphs — every figure must be a real value from the supplied NDAP material, with units and year. Sensational framing of real numbers is welcome; invented or embellished numbers are forbidden. (4) Then add a section headed '### The Take' with 1-3 bullet points; label each bullet '**Opinion:**' or '**Forecast:**' and derive each one only from the cited NDAP material (e.g. a straight-line extrapolation between the two years shown, stated as such). Opinions and forecasts may appear ONLY inside The Take. (5) Close with this exact italic disclaimer on its own final line: *The Take is interpretation, not data — every number above comes from the cited NDAP dataset(s).*",

  "scoop_sys_single": "You are an NDAP-only data journalist for India's National Data and Analytics Platform, writing a punchy, opinionated data story. Compute every figure ONLY from the supplied CSV rows of one NDAP dataset; use prior conversation only to interpret the question. Cite the dataset by its ID and as a clickable markdown link to https://ndap.niti.gov.in/dataset/<DATASET_ID>. Show the exact numbers you used (a small markdown table is ideal) and state units and year. Do not invent values absent from the rows. If a requested entity (city/year) is not present in the rows, say so explicitly and label it 'Low Confidence / Unverified'. If you had to combine, derive, or assume anything, flag those values with a caveat and state the assumption in plain language a non-technical reader can follow. Reply in the user's language.{{scoop_style}}{{markdown_latex}}{{india_scope}}{{ndap_hard_rule}}{{agg_guardrail}}",

  "scoop_metadata_sys": "You are an NDAP-only data journalist for India's National Data and Analytics Platform, writing a punchy, opinionated piece from dataset METADATA only — no rows were downloaded, so you may describe what the datasets contain but must not state specific figures. Answer using ONLY the supplied NDAP metadata; use prior conversation only to interpret the question. Cite every dataset you rely on by its ID and as a clickable markdown link to https://ndap.niti.gov.in/dataset/<DATASET_ID>, and also include the dataset's source URL if one is present in the supplied metadata. If you cannot point to a deterministic source (dataset ID or URL) for a statement, withhold it or label it 'Low Confidence / Unverified'. Do not invent raw values. Reply in the user's language. If NDAP evidence is insufficient, say so and name the dataset to download next.{{scoop_style}}{{markdown_latex}}{{ndap_hard_rule}}",

  "scoop_answer_ask": "Now write the final Scoop story in markdown — an H3 headline, a bold one-line lede, the story told through the actual numbers (units, year, and a citation of each dataset by ID), then a '### The Take' section whose bullets are each labeled '**Opinion:**' or '**Forecast:**' and derived from the cited rows, and the exact closing disclaimer line from your instructions. Do NOT reply with JSON or a tool request; just write the story. Write any formula as LaTeX in $…$ or $$…$$."

Verification (run these and paste output in your final report):
- python3 -c "import json; d = json.load(open('docs/assets/prompts.json')); print(sorted(k for k in d if k.startswith('scoop')))"
  Expected: ['scoop_answer_ask', 'scoop_metadata_sys', 'scoop_style', 'scoop_sys_single']
- python3 -c "import json; d = json.load(open('docs/assets/prompts.json')); assert '{{' not in d['scoop_style'], 'scoop_style must be token-free'; print('ok')"
  Expected: ok

Acceptance criteria (all must be true before reporting done):
- prompts.json parses as JSON.
- Exactly the four new keys exist with the exact text above; no existing key was modified.
- scoop_style contains no {{token}}.

If anything is ambiguous or a referenced symbol is missing, STOP and report — do not guess.
```

- Acceptance criteria:
  - `docs/assets/prompts.json` is valid JSON with the four new keys, text verbatim from this plan.
  - No existing key changed.

### Stream B: index.html HTML + CSS region (before the `<script>` tag)

- Files: `docs/index.html` — ONLY lines before `  <script>` (currently line 656)
- Depends on: Stream 0 (definitions only — can start immediately)
- Subagent prompt:

```
You are implementing Stream B: Scoop toggle HTML + CSS of a larger plan.
Other streams are running in parallel — do not touch files outside your list,
and inside docs/index.html do not touch anything at or after the line that
reads exactly "  <script>" (the inline app script — owned by another stream).

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: docs/index.html (HTML/CSS region only, before the inline <script>)
Files you may read for context: docs/index.html

Interface contract (frozen, do not change): the new button's data-mode value is
exactly "scoop"; its visible label is "Scoop"; its active color is #e8590c.

Tasks (do in order):

1. In the <style> block (~line 122), replace the comment line:
   /* Fast / Deep mode toggle (per chat) */
   with:
   /* Fast / Deep / Scoop mode toggle (per chat) */

2. In the same <style> block (~line 135), locate this seam:

    .mode-toggle button.active { background: #fff; color: var(--navy); box-shadow: 0 1px 3px rgba(25,44,109,.12); }
    .mode-toggle button[data-mode="deep"].active { color: var(--blue); }
    .mode-toggle button:disabled { cursor: not-allowed; opacity: .55; }

   Insert this line between the [data-mode="deep"] rule and the :disabled rule:

    .mode-toggle button[data-mode="scoop"].active { color: #e8590c; }

3. In the body markup (~line 585), locate the mode toggle seam:

          <button type="button" data-mode="deep">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            Deep
          </button>
        </div>

   Insert this third button (paste exactly, same indentation) between the Deep
   button's closing </button> and the closing </div>:

          <button type="button" data-mode="scoop">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
            Scoop
          </button>

4. In the composer hint (~line 599), replace the line:

      <div class="composer-hint">Enter to send · Shift+Enter for newline · Switch Fast/Deep anytime before sending · Key &amp; model live in Settings (top-right)</div>

   with:

      <div class="composer-hint">Enter to send · Shift+Enter for newline · Switch Fast/Deep/Scoop anytime before sending · Scoop is an opinionated data-journalism take · Key &amp; model live in Settings (top-right)</div>

Verification (run these and paste output in your final report):
- grep -c 'data-mode="scoop"' docs/index.html
  Expected: 2 (one CSS rule, one button)
- grep -n 'Switch Fast/Deep/Scoop anytime' docs/index.html
  Expected: one match in the composer-hint line.

Acceptance criteria (all must be true before reporting done):
- #modeToggle contains three buttons in order Fast, Deep, Scoop, all with the same markup shape.
- The scoop CSS rule sits directly after the deep rule, before the :disabled rule.
- No edits at or after the "  <script>" line.

If anything is ambiguous or a referenced symbol is missing, STOP and report — do not guess.
```

- Acceptance criteria:
  - Third toggle button with flame SVG and `data-mode="scoop"` present; CSS active rule `#e8590c`; hint text updated.
  - Zero changes inside the inline `<script>` region.

### Stream C: index.html script region (mode plumbing)

- Files: `docs/index.html` — ONLY the inline `<script>` block (currently lines 656–2604)
- Depends on: Stream 0 (definitions only — can start immediately; prompt keys are consumed at runtime, so Stream A need not be finished first)
- Subagent prompt:

```
You are implementing Stream C: Scoop mode plumbing in the app script of a larger plan.
Other streams are running in parallel — do not touch files outside your list,
and inside docs/index.html do not touch anything BEFORE the line that reads
exactly "  <script>" (HTML/CSS — owned by another stream).

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: docs/index.html (inline <script> region only)
Files you may read for context: docs/index.html, docs/assets/prompts.json

Interface contract (frozen, do not change):
- Mode string set: "fast" | "deep" | "scoop".
- New prompt keys (may not exist yet in prompts.json while streams run in
  parallel — reference them anyway): scoop_sys_single, scoop_metadata_sys,
  scoop_answer_ask.
- Signatures after your edits:
    function metadataMessages(question, candidates, histPreamble, mode)
    function dataInitialMessages(question, collected, histPreamble, mode)
    async function synthesizeWithDrilldown(question, collected, history, ui, mode, onDelta, maxOut)
    async function gatherFast(question, history, ui, mode = "fast")
- Final-answer temperature 0.9 for scoop only; the tool-loop call
  orComplete(messages, 0, 700) stays untouched.
- maxOut: deep 2800, scoop 2200, fast 1800. Deadlines unchanged.
- Do NOT edit: resolveTurnMode, agentWho, addAssistant, renderModeToggle,
  setBusy, the modeToggle click wiring, exportProvenance, newChatObject,
  loadChats, gatherDeep.

Tasks (do in order — locate each edit by the quoted seam, not the line number):

1. rememberTurn (~line 1477). Replace:
      const turnMode = mode === "deep" ? "deep" : "fast";
   with:
      const turnMode = mode === "deep" || mode === "scoop" ? mode : "fast";

2. chatMode (~line 1499). Replace the whole line:
    function chatMode() { const c = currentChat(); return c && c.mode === "deep" ? "deep" : "fast"; }
   with:
    function chatMode() { const c = currentChat(); return c && (c.mode === "deep" || c.mode === "scoop") ? c.mode : "fast"; }

3. setChatMode (~line 1503). Replace:
      c.mode = mode === "deep" ? "deep" : "fast";
   with:
      c.mode = mode === "deep" || mode === "scoop" ? mode : "fast";

4. modeLabel (~line 1661). Replace:
    function modeLabel(mode) {
      return mode === "deep" ? "Deep" : "Fast";
    }
   with:
    function modeLabel(mode) {
      return mode === "deep" ? "Deep" : mode === "scoop" ? "Scoop" : "Fast";
    }

5. metadataMessages (~line 2142). Replace:
    function metadataMessages(question, candidates, histPreamble) {
      return [
        { role: "system", content: P("metadata_sys") },
   with:
    function metadataMessages(question, candidates, histPreamble, mode) {
      return [
        { role: "system", content: P(mode === "scoop" ? "scoop_metadata_sys" : "metadata_sys") },
   (the user-message line below stays unchanged).

6. dataInitialMessages (~line 2151). Replace:
    function dataInitialMessages(question, collected, histPreamble, deep) {
      const sys = deep ? P("data_sys_multi") : P("data_sys_single");
   with:
    function dataInitialMessages(question, collected, histPreamble, mode) {
      const sys = mode === "deep" ? P("data_sys_multi") : mode === "scoop" ? P("scoop_sys_single") : P("data_sys_single");

7. synthesizeWithDrilldown (~line 2246). Replace:
    async function synthesizeWithDrilldown(question, collected, history, ui, deep, onDelta, maxOut) {
      const messages = dataInitialMessages(question, collected, convoBlock(history), deep);
   with:
    async function synthesizeWithDrilldown(question, collected, history, ui, mode, onDelta, maxOut) {
      const messages = dataInitialMessages(question, collected, convoBlock(history), mode);

8. Same function (~line 2270). Replace:
      const ANSWER_ASK = P("answer_ask");
      const answer = () => streamOrComplete(messages, 0, onDelta, maxOut);
   with:
      const ANSWER_ASK = mode === "scoop" ? P("scoop_answer_ask") : P("answer_ask");
      const answerTemp = mode === "scoop" ? 0.9 : 0;
      const answer = () => streamOrComplete(messages, answerTemp, onDelta, maxOut);
   Do NOT change the orComplete(messages, 0, 700) call earlier in the loop.

9. gatherFast (~line 2324). Replace:
    async function gatherFast(question, history, ui) {
   with:
    async function gatherFast(question, history, ui, mode = "fast") {
   And at the end of the same function (~line 2344) replace:
      return { messages: metadataMessages(question, candidates.slice(0, FAST_METADATA_CANDIDATES), pre), usedDataset: "" };
   with:
      return { messages: metadataMessages(question, candidates.slice(0, FAST_METADATA_CANDIDATES), pre, mode), usedDataset: "" };
   Do NOT edit gatherDeep or its metaFallback.

10. run() routing (~line 2473). Replace:
        const result = deep
          ? await gatherDeep(question, history, ui)
          : await gatherFast(question, history, ui);
    with:
        const result = deep
          ? await gatherDeep(question, history, ui)
          : await gatherFast(question, history, ui, modeUsed);

11. run() maxOut (~line 2485). Replace:
        const maxOut = deep ? 2800 : 1800;
    with:
        const maxOut = deep ? 2800 : modeUsed === "scoop" ? 2200 : 1800;

12. run() synthesis calls (~line 2493). Replace:
          finalText = await synthesizeWithDrilldown(question, result.collected, history, ui, deep, onDelta, maxOut);
        } else {
          finalText = await streamOrComplete(result.messages, 0, onDelta, maxOut);
    with:
          finalText = await synthesizeWithDrilldown(question, result.collected, history, ui, modeUsed, onDelta, maxOut);
        } else {
          finalText = await streamOrComplete(result.messages, modeUsed === "scoop" ? 0.9 : 0, onDelta, maxOut);
    Do NOT change the deadline lines (const deadlineMs = deep ? RUN_DEADLINE_DEEP_MS : RUN_DEADLINE_FAST_MS;) — scoop correctly inherits the Fast deadline.

Verification (run these and paste output in your final report):
- awk '/^  <script>$/{f=1;next} /^  <\/script>$/{f=0} f' docs/index.html > /tmp/scoop_app.js && node --check /tmp/scoop_app.js && echo SYNTAX_OK
  Expected: SYNTAX_OK
- grep -c 'scoop' docs/index.html
  Expected: at least 12 matches.

Acceptance criteria (all must be true before reporting done):
- All 12 edits applied; node --check passes on the extracted script.
- No occurrences of the old signatures remain: grep -n 'ui, deep, onDelta' docs/index.html returns nothing.
- Nothing before the "  <script>" line was modified.

If anything is ambiguous or a referenced symbol is missing, STOP and report — do not guess.
```

- Acceptance criteria:
  - Extracted script passes `node --check`.
  - All mode plumbing widened per the contract; no edits outside the script region; `gatherDeep`, deadlines, and tool-loop temperature untouched.

### Stream D: README docs

- Files: `README.md`, `docs/README.md`
- Depends on: Stream 0 (definitions only — can start immediately)
- Subagent prompt:

```
You are implementing Stream D: README docs for Scoop mode of a larger plan.
Other streams are running in parallel — do not touch files outside your list.

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: README.md, docs/README.md
Files you may read for context: README.md, docs/README.md

Interface contract (frozen, do not change): mode name "Scoop"; it reuses the
Fast gathering pipeline and the Fast 2-minute deadline; opinions/forecasts live
in a labeled "The Take" section; every number still comes from NDAP.

Tasks (do in order):

1. README.md (~line 18): in the bullet beginning "- A static GitHub Pages chat
   demo", replace the phrase:
     Each answer runs in one of two modes via a **Fast / Deep** toggle,
   with:
     Each answer runs in one of three modes via a **Fast / Deep / Scoop** toggle,

2. README.md (~line 20): directly after the sub-bullet that begins
     - **Deep**: a bounded research loop —
   (and before the "- Utilities to harvest" bullet), add this sub-bullet at the
   same indentation as the Fast/Deep sub-bullets:
     - **Scoop**: the Fast pipeline with a data-journalist voice — headline, bold lede, the story told through the numbers, plus a labeled "The Take" section for opinions and forecasts derived from the cited rows. Every figure is still NDAP-only.

3. README.md (~line 115): replace the sentence:
     Each answer is **Fast** or **Deep**, chosen with the toggle in the header (top of the chat).
   with:
     Each answer is **Fast**, **Deep**, or **Scoop**, chosen with the toggle in the header (top of the chat).

4. README.md (~line 118): directly after the "- **Deep** — …" bullet (which ends
   "at higher latency and cost.") and before the paragraph starting "While an
   answer is running", add this bullet:
     - **Scoop** — the Fast pipeline with a data-journalist persona: an H3 headline, a bold one-line lede, the story told through real NDAP numbers, then a "The Take" section whose bullets are labeled *Opinion* or *Forecast* and derived from the cited rows, closing with a one-line disclaimer. Same latency profile and 2-minute ceiling as Fast; answers are creative in tone but never in the numbers.

5. docs/README.md (~line 15): replace the table row:
     | `index.html` | Browser chat UI (Fast / Deep modes, per-turn mode tracking, Stop button, and run deadlines) |
   with:
     | `index.html` | Browser chat UI (Fast / Deep / Scoop modes, per-turn mode tracking, Stop button, and run deadlines) |

6. docs/README.md (~line 29): replace the sentence:
     Fast runs have a 2-minute wall-clock ceiling; Deep runs have a 5-minute ceiling.
   with:
     Fast and Scoop runs have a 2-minute wall-clock ceiling; Deep runs have a 5-minute ceiling.

Verification (run these and paste output in your final report):
- grep -n 'Scoop' README.md docs/README.md
  Expected: matches in README.md (three places) and docs/README.md (two places).

Acceptance criteria (all must be true before reporting done):
- All six edits applied with the exact replacement text.
- No other lines changed.

If anything is ambiguous or a referenced symbol is missing, STOP and report — do not guess.
```

- Acceptance criteria:
  - Both READMEs mention the third mode with the exact prose above; nothing else altered.

### Stream E: test_queries.py scoop support

- Files: `scripts/test_queries.py`
- Depends on: Stream 0 (definitions only — can start immediately)
- Subagent prompt:

```
You are implementing Stream E: --mode scoop in the headless test runner of a larger plan.
Other streams are running in parallel — do not touch files outside your list.

Repo root: /Users/jigar/projects/messing-around/yutori-ndap
Files you may edit: scripts/test_queries.py
Files you may read for context: scripts/test_queries.py, docs/assets/prompts.json

Interface contract (frozen, do not change):
- Mode strings: "fast" | "deep" | "scoop". Prompt keys consumed:
  scoop_sys_single, scoop_metadata_sys, scoop_answer_ask (they may not exist in
  prompts.json yet while streams run in parallel — reference them anyway).
- Signatures after your edits:
    def metadata_messages(question, candidates, mode="fast")
    def data_initial_messages(question, collected, mode)
    def synthesize_with_drilldown(model, question, collected, mode)
    def gather_fast(model: str, question: str, mode: str = "fast") -> dict
- Final answer: temperature 0.9 and max_tokens 2200 for scoop; temperature 0
  and max_tokens 3000 otherwise. Tool-loop chat(model, messages, 0, 700) stays
  untouched.
- gather_deep keeps its current synthesis behavior exactly: it must pass
  "deep" if len(collected) > 1 else "fast" (mirroring the old
  deep=len(collected) > 1 heuristic).

Tasks (do in order — locate each edit by the quoted seam, not the line number):

1. Module docstring (line 3): replace:
   NDAP query regression TEST — a headless mirror of the docs/index.html Fast & Deep
   with:
   NDAP query regression TEST — a headless mirror of the docs/index.html Fast, Deep & Scoop

2. metadata_messages (~line 311). Replace:
   def metadata_messages(question, candidates):
       return [
           {"role": "system", "content": P("metadata_sys")},
   with:
   def metadata_messages(question, candidates, mode="fast"):
       return [
           {"role": "system", "content": P("scoop_metadata_sys" if mode == "scoop" else "metadata_sys")},
   (the user-message line stays unchanged).

3. data_initial_messages (~line 486). Replace:
   def data_initial_messages(question, collected, deep):
       sys = P("data_sys_multi") if deep else P("data_sys_single")
   with:
   def data_initial_messages(question, collected, mode):
       sys = P("data_sys_multi") if mode == "deep" else (P("scoop_sys_single") if mode == "scoop" else P("data_sys_single"))

4. synthesize_with_drilldown (~line 551). Replace:
   def synthesize_with_drilldown(model, question, collected):
       messages = data_initial_messages(question, collected, deep=len(collected) > 1)
   with:
   def synthesize_with_drilldown(model, question, collected, mode):
       messages = data_initial_messages(question, collected, mode)

5. Same function (~line 567). Replace:
       answer_ask = P("answer_ask")
       messages.append({"role": "user", "content": answer_ask})
       final = chat(model, messages, 0, 3000)
   with:
       answer_ask = P("scoop_answer_ask") if mode == "scoop" else P("answer_ask")
       answer_temp = 0.9 if mode == "scoop" else 0
       answer_max = 2200 if mode == "scoop" else 3000
       messages.append({"role": "user", "content": answer_ask})
       final = chat(model, messages, answer_temp, answer_max)
   And in the stray-action retry loop a few lines below (~line 578) replace:
           final = chat(model, messages, 0, 3000)
   with:
           final = chat(model, messages, answer_temp, answer_max)
   Do NOT change the tool-loop call chat(model, messages, 0, 700).

6. gather_fast (~line 583). Replace:
   def gather_fast(model: str, question: str) -> dict:
       trace = {"mode": "fast"}
   with:
   def gather_fast(model: str, question: str, mode: str = "fast") -> dict:
       trace = {"mode": mode}
   In the same function (~line 601) replace:
           trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, [got])
   with:
           trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, [got], mode)
   And in its download-failed fallback (~line 606) replace:
           trace["answer"] = chat(model, metadata_messages(question, slim(candidates[:FAST_METADATA_CANDIDATES])), 0, 2000)
   with:
           trace["answer"] = chat(model, metadata_messages(question, slim(candidates[:FAST_METADATA_CANDIDATES]), mode), 0.9 if mode == "scoop" else 0, 2000)

7. gather_deep (~line 651). Replace:
           trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, collected)
   with:
           trace["answer"], trace["drills"] = synthesize_with_drilldown(model, question, collected, "deep" if len(collected) > 1 else "fast")
   Leave gather_deep's metadata_messages fallback call (~line 655) unchanged.

8. run_one (~line 659). Replace:
   def run_one(model: str, mode: str, question: str) -> dict:
       return gather_deep(model, question) if mode == "deep" else gather_fast(model, question)
   with:
   def run_one(model: str, mode: str, question: str) -> dict:
       return gather_deep(model, question) if mode == "deep" else gather_fast(model, question, mode)

9. Argparse (~line 665). Replace:
       ap.add_argument("--mode", choices=["fast", "deep"], help="Mode for --query/--homepage/--srit items (suite items carry their own).")
   with:
       ap.add_argument("--mode", choices=["fast", "deep", "scoop"], help="Mode for --query/--homepage/--srit items (suite items carry their own).")

Verification (run these and paste output in your final report):
- python3 -m py_compile scripts/test_queries.py && echo COMPILE_OK
  Expected: COMPILE_OK
- python3 scripts/test_queries.py --help | grep -o "{fast,deep,scoop}"
  Expected: {fast,deep,scoop}

Acceptance criteria (all must be true before reporting done):
- File compiles; --mode accepts scoop; all nine edits applied.
- The built-in SUITE, deep gathering loop, and tool-loop temperatures are unchanged.

If anything is ambiguous or a referenced symbol is missing, STOP and report — do not guess.
```

- Acceptance criteria:
  - `python3 -m py_compile` passes; `--mode scoop` accepted; deep/fast behavior byte-identical to before for non-scoop runs.

## Integration step (sequential, single executor)

- Trigger: all of Streams A, B, C, D, E reported success.
- Files touched: none expected (fix-ups only if checks fail); reads all five stream outputs.
- Tasks:
  1. **Wiring check — prompt keys.** Run:
     `python3 -c "import json,re; d=json.load(open('docs/assets/prompts.json')); resolved=re.sub(r'\{\{(\w+)\}\}', lambda m: d.get(m.group(1),''), d['scoop_sys_single']); assert 'HARD RULE' in resolved and 'SCOOP VOICE' in resolved and 'aggregation rule' in resolved; resolved2=re.sub(r'\{\{(\w+)\}\}', lambda m: d.get(m.group(1),''), d['scoop_metadata_sys']); assert 'HARD RULE' in resolved2 and 'SCOOP VOICE' in resolved2; print('PROMPTS_OK')"`
     Expected: `PROMPTS_OK`. If a token fails to resolve, fix the key name in `prompts.json` to match the contract in Stream 0 (the contract wins).
  2. **Conflict resolution — index.html regions.** Streams B and C both edited `docs/index.html` with disjoint regions. Confirm the boundary held: `grep -n 'data-mode="scoop"' docs/index.html` must show exactly one match before the `  <script>` line (the button; the CSS rule also precedes it) and none after inside HTML. Then re-run the script syntax check:
     `awk '/^  <script>$/{f=1;next} /^  <\/script>$/{f=0} f' docs/index.html > /tmp/scoop_app.js && node --check /tmp/scoop_app.js && echo SYNTAX_OK`
     Expected: `SYNTAX_OK`. If both streams somehow touched the same lines, re-apply the losing stream's edit exactly as specified in its stream section.
  3. **Type/behavior reconciliation.** `python3 -m py_compile scripts/test_queries.py` and confirm no stale call sites: `grep -n 'synthesize_with_drilldown(model, question, collected)$' scripts/test_queries.py` and `grep -n 'ui, deep, onDelta' docs/index.html` must both return nothing.
  4. **End-to-end headless smoke** (requires `OPENROUTER_API_KEY=` in the repo-root `.env`; network access to openrouter.ai and the NDAP proxy):
     `python3 scripts/test_queries.py --mode scoop --query "What was India's total slum population in 2011?"`
     Pass condition: prints `status=ok`, exits 0, and the saved JSON's `answer` contains the substring `The Take` and a `ndap.niti.gov.in/dataset/` citation. If the run fails on network/credits, report it as an environment blocker — do not change code.
     Regression guard: `python3 scripts/test_queries.py --mode fast --query "What was India's total slum population in 2011?"` still prints `status=ok`.
  5. **Browser smoke.** Serve the app: `python3 -m http.server 8080 --directory docs` (run in the background), open `http://localhost:8080/`, and verify: (a) the toggle shows Fast / Deep / Scoop and clicking Scoop turns that button orange; (b) with an OpenRouter key configured in Settings, a Scoop question streams an answer that starts with an `###` headline and ends with the disclaimer line, and the answer's badge reads `SCOOP`; (c) Fast and Deep answers look unchanged; (d) reload the page — the chat's Scoop selection persists. Stop the server afterwards.
- Acceptance criteria:
  - All five checks pass (or step 4/5 blocked only by missing key/network, explicitly reported).
- Rollback plan: this work lives on its own branch — `git checkout -- .` for uncommitted fix-ups, or revert/abandon the branch; `main` and the deployed Pages app are untouched until merge.

## Verification step

Run from the repo root, in order:

| Command | Pass condition |
|---|---|
| `python3 -c "import json; json.load(open('docs/assets/prompts.json'))" && echo JSON_OK` | prints `JSON_OK` |
| `awk '/^  <script>$/{f=1;next} /^  <\/script>$/{f=0} f' docs/index.html > /tmp/scoop_app.js && node --check /tmp/scoop_app.js && echo SYNTAX_OK` | prints `SYNTAX_OK` |
| `python3 -m py_compile scripts/test_queries.py && echo COMPILE_OK` | prints `COMPILE_OK` |
| `grep -c 'data-mode="scoop"' docs/index.html` | prints `2` |
| `python3 scripts/test_queries.py --mode scoop --query "What was India's total slum population in 2011?"` | `status=ok`, exit code 0; saved JSON answer contains `The Take`, `Opinion` or `Forecast`, the disclaimer line, and a `ndap.niti.gov.in/dataset/` link |
| `python3 scripts/test_queries.py --mode fast --query "What was India's total slum population in 2011?"` | `status=ok`, exit code 0 — Fast regression unchanged |
| Manual, via `python3 -m http.server 8080 --directory docs`: three-mode toggle renders; Scoop active state is orange with flame icon; Scoop answer = H3 headline → bold lede → numbers → `### The Take` (labeled bullets) → italic disclaimer; mode badge shows `SCOOP`; the per-chat mode selection survives a reload; Fast and Deep behave exactly as before | all observations true |
