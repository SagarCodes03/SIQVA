# AGENTS.md — ArgoCard (FloatChat-R)

Instructions for coding agents (Codex, Antigravity, etc.) working in this repo.
Read this file fully before every task. If a task conflicts with it, stop and ask.

## 1. Project in one paragraph

ArgoCard turns a natural-language Argo question into a validated, QC-explicit
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

Python 3.11+, FastAPI, Streamlit, Pydantic (spec schema), argopy, xarray,
pandas, Parquet (cache), SQLite (stored cards), Plotly, pytest, rapidfuzz,
dateparser. LLM: local Llama 3.2 3B via Ollama, behind one interface (below).

## 5. Architecture

```
Streamlit UI -> FastAPI -> Parser -> Validator -> Fetcher (argopy)
                                         |             |
                                  Gazetteer/schema   ERDDAP / GDAC
                           QC+mode filter -> Analyzer -> Plot templates
                                         |
                        Query card builder -> SQLite + Parquet cache
```

Suggested layout:

```
src/argocard/
  spec.py          # Pydantic QuerySpec + enums
  validator.py     # bounds, dates, variable allow-list, size caps
  gazetteer.py     # region name -> bounding box (+ fuzzy match)
  rules_parser.py  # dates, variables, mode, intent via rules
  llm_parser.py    # constrained-output fallback (Ollama)
  parser.py        # parse(question) -> QuerySpec | ClarificationNeeded
  fetcher.py       # argopy access, caching by spec hash
  qc.py            # mode / QC filtering
  analyzer.py      # stats + coverage metadata
  plots.py         # profile, map, T-S templates
  card.py          # query card + generated script + re-run/diff
  api.py           # FastAPI
app/ui.py          # Streamlit
benchmark/         # questions + reference specs + scorer
tests/
```

## 6. Parser design (important for a 3B model)

- Hybrid: **rules first, LLM only for what rules leave unfilled.**
  - Dates: `dateparser` / regex. Variables: synonym dictionary to Argo names
    (TEMP, PSAL, PRES). Region: gazetteer + fuzzy match, or coordinate regex.
    Mode/QC: default `research`; change only on explicit user words
    ("real-time", "all data"). Intent: keyword rules, LLM as tie-breaker.
- LLM calls: temperature 0, JSON-schema-constrained output (generate the
  schema from the Pydantic model; use Ollama's `format` option), short prompt,
  4-6 examples, one field per call if accuracy is low.
- The public interface is a single function `parse(question) -> QuerySpec`.
  Keep the LLM backend swappable so models can be compared on the benchmark.
- If validation fails after one retry, return a clarification request. Never
  guess a region, date range, or QC mode.

## 7. Spec and validation

`QuerySpec` fields: `region` (bbox), `date_range`, `variables`, `depth_range`,
`mode` (`research` | `standard` | `expert`), `intent`
(`profile` | `map` | `ts` | `trend`). The validator enforces: valid bbox, date
order, allowed variables, and a maximum request size. Oversized requests get a
suggestion to narrow region or window, not a silent truncation.

## 8. Fetching, caching, reproducibility

- Normalise the spec, hash it, and use the hash as the cache key (Parquet).
- Record source (ERDDAP/GDAC), argopy and xarray versions, fetch timestamp, and
  a data hash in every card.
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

`benchmark/` holds questions with reference specs. The scorer reports per-field
accuracy, QC/mode correctness, region overlap, reproducibility rate, latency,
and which fields needed the LLM. Baselines: LLM answering directly, and LLM
generating argopy code without a validator. Do not change reference specs to
make scores pass.

## 11. When uncertain

Stop and ask rather than adding features, dependencies, or assumptions.
Prefer the simplest implementation that satisfies the task and the rules above.

Float index cache (allowed): A local Parquet snapshot of float metadata (WMO, last position, date, type), fetched via argopy IndexFetcher, used only for discovery (“floats near X”) and map display. Record the fetch date. Never use it for profile values.