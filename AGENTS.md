# AGENTS.md — SIQVA
*(formerly ArgoCard / FloatChat-R)*

Instructions for coding agents (Codex, Antigravity, etc.) working in this repo.
Read this file fully before every task. If a task conflicts with it, stop and ask.

## 1. Project in one paragraph

SIQVA turns a natural-language Argo question into a validated, QC-explicit
**query spec**, fetches real data through established Argo access tools, draws
standard plots, and returns a reproducible **query card** (exact parameters,
data mode, QC filter, source, library versions, timestamp, data hash, runnable
script). The LLM only translates language into a spec. Everything else is
deterministic.

## 2. Hard rules (never violate)

1. **The LLM never sees data values.** It receives only the user question, the
   spec schema, and small lookup lists (e.g. candidate region names). Never put
   profile data, statistics, or fetched results into a prompt.
2. **All numbers in answers come from code.** Summaries are deterministic
   templates, not LLM text.
3. **QC flags and data mode are never silently ignored.** Every spec has an
   explicit `mode` (default `research`) and QC setting, and both appear in the
   answer and the query card.
4. **Do not invent APIs, parameters, datasets, or library features.** Before
   using any argopy / xarray / Plotly call, confirm it against installed
   package docs (`help()`, `pip show`, source) or run it on a tiny real fetch.
   If unsure, say so in the PR notes instead of guessing.
5. **Do not add technologies not listed in Section 4** without asking.
6. **No secrets in the repo.** Use environment variables; keep `.env` ignored.

## 3. Do NOT build (scope control)

Forecasting or anomaly detection; vision-language image input; AR or 3D globe;
multi-user collaboration; user accounts or auth; PostGIS, vector databases, or
custom ETL pipelines; model fine-tuning; BGC or Deep Argo support (post-MVP);
offline mode. Do not claim accuracy figures (e.g. "100%") in code, docs, or UI.

## 4. Stack

Python 3.11+, Streamlit, Pydantic (spec schema), argopy, xarray,
pandas, Parquet (cache), SQLite (stored cards), Plotly, pytest, rapidfuzz,
dateparser, gsw. LLM: local Llama 3.2 3B via Ollama, behind one interface (below).

## 5. Architecture

```
Streamlit UI -> Parser -> Validator -> Fetcher (argopy)
                              |             |
                       Gazetteer/schema   ERDDAP / GDAC
                QC+mode filter -> Analyzer -> Plot templates
                              |
             Query card builder -> SQLite + Parquet cache
```

Suggested layout:

```
src/siqva/
  spec.py          # Pydantic QuerySpec + enums
  validator.py     # bounds, dates, variable allow-list, size caps (structural)
  capabilities.py  # capability profiles (METADATA, SAMPLE_ALLOWED, FULL_REQUIRED)
  planner.py       # layered execution planning (FULL, CHUNKED, SAMPLE, REFUSE)
  floatindex.py    # local float index query, counts, overview maps, deterministic sampling
  regions.py       # safe region description and bbox resolution
  gazetteer.py     # region name -> bounding box (+ fuzzy match)
  rules_parser.py  # dates, variables, mode, intent via rules
  llm_parser.py    # constrained-output fallback (Ollama)
  parser.py        # parse(question) -> QuerySpec | ClarificationNeeded
  interpretation.py# deterministic "Understood as" formatting
  pipeline.py      # top-level error handling and execution pipeline
  fetcher.py       # argopy access, caching by spec hash, per-profile sampling
  chunking.py      # large-query calendar-month splitting and assembly
  qc.py            # mode / QC filtering
  analyzer.py      # stats + coverage metadata (regional stats suppressed on samples)
  operations.py    # deterministic operations (mean, min, max, anomaly)
  comparison.py    # dual-dataset comparison without anomaly claims
  glossary.py      # scientific term lookup with literature citations and verification flag
  router.py        # query intent router (data, op, compare, glossary, meta)
  followup.py      # conversational state and query edits (salinity, year, region)
  plots.py         # profile, map, T-S, overview map templates
  card.py          # query card + generated script + re-run/diff
app/ui.py          # Streamlit
benchmark/         # questions + reference specs + scorer
tests/
```

## 6. Parser design (important for a 3B model)

- Hybrid: **rules first, LLM only for what rules leave unfilled.**
  - Dates: `dateparser` / regex.
    - Resolves numeric relative phrases (`past/last N days/weeks/months/years`) using anchor `today`, ending at `today`.
    - Resolves `since <date>` ending at `today`.
    - Resolves explicit year patterns: single years (`in 2022`, `for 2022`, `during 2022`, `all of 2022`, `the whole of 2022`, `year 2022` -> `YYYY-01-01` to `YYYY-12-31`), year ranges (`2021-2023`, `between 2021 and 2023`), month-year (`March 2023`), month ranges (`Jan to March 2022`), and ISO ranges.
    - Rejects with clarification any future-ending dates (`requested range ends in the future`).
    - Rejects with clarification adjacent ambiguous months lacking connectors (`April march 2025`).
    - Rejects with clarification unquantified relative terms (`last month`, `this month`, `this year`, `last year`, `recent`, `recently`) and bare months without years (`in March`): requires explicit year or date range.
  - Variables: synonym dictionary to Argo names (TEMP, PSAL, PRES).
  - Region: gazetteer + fuzzy match, or coordinate regex.
    - Coordinate regex (e.g. `10N-20N, 60E-70E`) resolves directly to bounding box.
    - Exact canonical name and alias lookup (e.g. `Arabian Sea`).
    - Directional/generic word guards prevent matching pure direction words.
    - Three clarification cases: (1) no region specified (lists supported regions or coordinates); (2) unsupported region (e.g. `Pacific`, `South Atlantic`, lists supported regions); (3) ambiguous region (lists close candidates, e.g. `Did you mean 'Arabian Sea' or 'Mediterranean Sea'`).
    - Dedicated Pacific guard: "Pacific Ocean" alone returns a dedicated message explaining the basin is too large for one query and crosses 180°, directing the user to supported Pacific regions (`Eastern equatorial Pacific`, `Nino 3.4`, `Nino 3`, `Nino 1+2`) or coordinates.
    - Supported Pacific sub-regions: `Nino 1+2` (0°–10°S, 90°W–80°W), `Nino 3` (5°N–5°S, 150°W–90°W), and `Nino 3.4` (5°N–5°S, 170°W–120°W) using NOAA Climate Prediction Center (CPC) definitions. `Nino 4` is omitted because it crosses the antimeridian.
    - The bounding box is **never guessed**. If unknown or ambiguous, `bbox=None` is returned.
  - Mode/QC: default `research`; change only on explicit user words ("real-time", "all data").
  - Intent: keyword rules, LLM as tie-breaker.
- Query interpretation ("Understood as"):
  - `src/siqva/interpretation.py` formats resolved fields with provenance labels (`[rules]`, `[llm]`, `[default]`).
  - Rendered in Streamlit UI via `st.caption(...)` above both successful results and clarification requests.
- LLM calls: temperature 0, JSON-schema-constrained output (generate the
  schema from the Pydantic model; use Ollama's `format` option), short prompt,
  4-6 examples, one field per call if accuracy is low.
- The public interface is a single function `parse(question) -> QuerySpec`.
  Keep the LLM backend swappable so models can be compared on the benchmark.
- If validation fails after one retry, return a clarification request. Never
  guess a region, date range, or QC mode.

## 7. Spec, validation, and planning

`QuerySpec` fields: `region` (bbox or basin), `date_range`, `variables`, `depth_range`,
`mode` (`research` | `standard` | `expert`), `intent`
(`profile` | `map` | `ts` | `trend` | `thermocline` | `tchp` | `acoustic`).

Layered validation and planning:
- Structural validation (`validator.py`): enforces valid bounds, chronological date ordering, allowed variables, depth ranges, and basic syntax. Bounding boxes crossing the antimeridian (180° meridian, where `lon_min > lon_max`) are rejected with an explicit plain-words explanation.
- Capability profiles (`capabilities.py`): classifies each intent as `METADATA` (e.g. float overview maps, counts), `SAMPLE_ALLOWED` (e.g. profile, ts, acoustic), or `FULL_REQUIRED` (e.g. trend, thermocline, tchp, operations, comparison). Caps maximum requested depth at 2000 dbar.
- Execution planning (`planner.py`): evaluates the validated spec against capability rules, region geometry, and float-index profile counts. Emits a `PlanDecision` (`FULL`, `CHUNKED`, `SAMPLE`, `REFUSE`).
- No-dead-ends rule: Every refusal (`REFUSE`) must provide actionable, structured options (e.g. smaller subregions, shorter time period, overview float map, sample if permitted), never a blank refusal.

Physics intents (on-demand TEOS-10 analysis via `gsw`):
- `thermocline`: Mixed Layer Depth (MLD), Isothermal Layer Depth (ILD), Barrier Layer Thickness (BLT), and 20°C isotherm (Z20).
- `tchp`: Tropical Cyclone Heat Potential integrated relative to the 26°C isotherm (Z26).
- `acoustic`: TEOS-10 sound speed profile, Sonic Layer Depth (SLD), and deep SOFAR channel axis.

Physics runs *only* on those three intents; standard queries (`profile`, `map`, `ts`, `trend`) skip all physics calculations and plots.
Water-mass classification was permanently removed because it was Indian-Ocean-only and gave wrong, misleading labels elsewhere.

## 8. Fetching, caching, reproducibility, and sampling

- Normalise the spec, hash it, and use the hash as the cache key (Parquet).
- Large multi-month queries exceeding the single-request cost cap (15,000) are decomposed into calendar-month chunks up to `SIQVA_MAX_CHUNKS` (default 24). Each month is fetched and cached independently via standard Parquet cache, enabling shared reuse across overlapping queries. Combined data is deduplicated by `(PLATFORM_NUMBER, CYCLE_NUMBER, PRES, TIME)` and capped by `SIQVA_MAX_TOTAL_ROWS` (default 3,000,000). If any single month exceeds 15,000 cost cap, chunking cannot save it and the standard oversized suggestion applies.
- Deterministic profile sampling (`fetch_sample`): when the planner chooses `SAMPLE`, space-time stratified profile picks are selected deterministically via `FloatIndex.select_sample` using a seed derived from `(fetch_key, build_date)`. Profiles are fetched sequentially with single-profile caching (`mode, variables, wmo, cycle`) within a 90-second foreground wall-clock budget.
- **Samples are never region statistics:** The analyzer strictly suppresses regional statistics, area averages, and physics summaries on sample runs. Per-profile display and plots are permitted, but samples must never be presented as regional aggregates.
- Query card and reproducibility:
  - Record source (ERDDAP/GDAC), argopy and xarray versions, fetch timestamp, and a data hash in every card.
  - Query cards record `plan_decision` and, for samples, the `sample_picks` list, method, seed, and index build date.
  - `generate_script` generates standalone reproducible code: for samples, it fetches the exact picked profiles without requiring the float index and explicitly states in its header that it reproduces the sample, not the region.
  - Re-run reproduces the exact same sample picks and diffs data hashes.
  - Compare Runs (`/compare`) compares only complete runs (`FULL` or `CHUNKED`). Samples cannot be compared as regional datasets and display clear explanatory options.
- `QueryCard` persists an optional `question` field in SQLite (`data/cards.sqlite`), with automatic migration (`ALTER TABLE`) for legacy databases. Cards for chunked queries record `chunks`, and `generate_script` generates a reproducible loop over monthly chunks.
- `list_cards()` deduplicates entries by `(spec_hash, mode)` returning newest cards.
- Sidebar history label format: `"{question} · {created_at[:10]} · {region_name}"` (question truncated to 40 characters, falling back to `"{Intent} query"`).
- Clicking a history entry restores card metadata, spec, generated script, and re-renders plots and analysis from local Parquet cache (if parquet is missing, displays metadata and a re-run prompt). Optional `session_id` isolates history when `SIQVA_SHARED_HISTORY=0`.
- Re-run recomputes the fetch and compares hashes. If data differs, report a
  diff summary (e.g. new delayed-mode corrections). A change is not an error.
- Cached results must be labelled as cached in the UI.
- Failures: timeout or oversize -> clear message plus suggestion; empty
  result -> say so and draw no empty plot.

## 9. Workflow for agents

1. One module per task, in this order: spec + validator -> gazetteer ->
   rules parser -> fetcher + QC filter -> card builder -> plots -> LLM
   fallback -> UI.
2. Every module ships with pytest tests. Run `pytest` before declaring done.
3. Fetcher tests run against a small, fixed region/time window and a recorded
   fixture so CI does not hammer remote servers.
4. Keep diffs small and focused. Do not refactor unrelated files.
5. In each PR/summary, list: what changed, what was verified, what was *not*
   verified (especially any external API call).
6. Style: type hints, docstrings on public functions, `ruff` + `black`.

## 10. Evaluation (do not break)

`benchmark/` holds questions with reference specs. Benchmark questions carry a `split` field (`dev` for internal regression smoke tests, `heldout` reserved). The scorer reports per-field accuracy, QC/mode correctness, region overlap, reproducibility rate, per-split metrics, parser-only latency, and warns on sample sizes < 30. Baselines: LLM answering directly, and LLM generating argopy code without a validator. Do not change reference specs to make scores pass. Do not present internal regression test results as general system accuracy.

## 11. When uncertain

Stop and ask rather than adding features, dependencies, or assumptions.
Prefer the simplest implementation that satisfies the task and the rules above.

Float index cache (allowed): A local Parquet snapshot of float metadata (`data/float_index.parquet`), loaded once via `FloatIndex` (`src/siqva/floatindex.py`), used strictly for discovery ("floats near X"), overview maps, profile counts, and deterministic stratified space-time profile sampling (`select_sample`). Record the index build date. **Never use it for profile values.**