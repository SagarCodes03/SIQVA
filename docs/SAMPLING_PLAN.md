# SAMPLING PLAN (read fully at the start of every session)

Project SIQVA: natural-language questions become validated, QC-explicit Argo query
specs, fetched with argopy, shown with plots, deterministic answer text and a
reproducible query card. A local LLM (Ollama) is ONLY a translator from language to
structured fields; it NEVER sees data values, statistics or results. All answer text
comes from fixed templates. QC and mode are never silently ignored. Python 3.11,
Windows, Pydantic, argopy, pandas, Plotly, Streamlit (app/ui.py), SQLite + Parquet
cache, code in src/siqva/. The owner is a beginner: reports in plain English.
Branch: task-s-sampling.

## PROBLEM
Validation rejects requests only because area x days x depth is large. Float position
maps download no observations yet are rejected as "too large". Large requests that
bypass the guard end in a session timeout. A name-only basin ("Pacific Ocean") is a
dead end. Every rejection must offer an action that works.

## DESIGN (decided with the owner)
1. Layered validation instead of one cost rule:
   a) STRUCTURE (hard errors only): invalid region, dates out of order, depth outside
      0-2000 dbar, disallowed variables, ambiguous input needing clarification. Size
      is never a structural error.
   b) REQUEST KIND: metadata requests (float positions, counts) use only the local
      float index and skip every size check.
   c) PLAN (observation requests only): decide FULL, CHUNKED, SAMPLE or REFUSE from
      the profile count in the local float index, SAME thresholds for every region
      (never region name or area). The old geometric cost formula is only a fallback
      when the index does not cover the request, with profile_count_verified False.
      "Reject" only means invalid input.
2. Capability profile per plot module; validation adapts to it:
   | module (intent)                  | data need                       | default depth |
   | Temperature vs Depth (profile)   | SAMPLE_OK                       | 0-500 |
   | Salinity vs Depth (profile PSAL) | SAMPLE_OK                       | 0-500 |
   | Temperature vs Salinity (ts)     | SAMPLE_OK                       | 0-500 |
   | Float Position Map (map)         | METADATA                        | none |
   | Thermocline & Barrier Layer      | SAMPLE_OK, per-profile only     | 0-500 |
   | Cyclone Heat Potential           | SAMPLE_OK, per-profile only     | 0-500 |
   | Acoustic Sound Speed             | SAMPLE_OK, per-profile only     | 0-2000 |
   | Buoyancy & Stability             | SAMPLE_OK, per-profile only     | 0-500 |
   | T-S with Isopycnals              | SAMPLE_OK                       | 0-500 |
   | Oxygen Minimum Zone              | SAMPLE_OK, per-profile only     | keep current default |
   | Hovmoller Diagram                | FULL_REQUIRED                   | 0-500 |
   | Climatology Envelope             | FULL_REQUIRED                   | 0-500 |
   | Float Drift Velocity             | FULL_REQUIRED                   | keep current default |
   FULL_REQUIRED: a sample is never allowed; if too large, REFUSE with working options.
   SAMPLE_OK: a sample is shown only as plots of individual profiles, never regional
   statistics. A default depth applies only when the user gave none, is flagged
   "(default)", and a user depth always wins.
3. A SAMPLE is for plots only. Unit = one profile (WMO + cycle), never a whole float.
   Default 12 profiles, steps (12, 24, 48), hard max 50 (constants SAMPLE_DEFAULT,
   SAMPLE_STEPS, SAMPLE_MAX). Spread evenly over space (grid cells) and time (slices),
   distinct floats preferred, delayed-mode profiles only in research mode (if fewer
   exist say how many and suggest standard mode), deterministic (seed from fetch key
   plus index build date). Always shown with the overview map from the index and the
   label: "Sample: n of N profiles in this region and period, selected evenly across
   space and time. Not representative of the whole region." No mean, extreme, count or
   physics summary of the REGION is computed from a sample. Data questions on a
   too-large region are refused with: "A region-wide statistic needs all profiles; a
   sample would not represent it." plus working options.
4. Every result is labelled "Full: all N profiles" or "Sample: n of N profiles".

## RULES (all tasks)
- Never invent facts about the code or library APIs: read the code, check installed
  packages. Be economical: use git grep and line ranges; do not re-read whole large
  files (app/ui.py, plots.py, fetcher.py).
- The LLM never sees data values; no new LLM calls in this work.
- Never push to main, never force-push, never rewrite history, never stage .env,
  cache/, logs/, *.sqlite, data/*.parquet, data/raw/. Do not revert anyone's changes.
- No network access and no Ollama for you. Use fixtures, mocks, synthetic data. Never
  download anything. Tests must not touch the network.
- No questions to the owner: choose the conservative option and log it in
  docs/DECISIONS.md (date, task, decision, reason).
- Run pytest in the background with output to a file; stop and report if there is no
  new output for 2 minutes:
  pytest -q -o faulthandler_timeout=60 > scripts/review/pytest_out.txt 2>&1
- Commit small steps inside a task. After each task: tests green, commit, tag
  done-S<n>, git push -u origin task-s-sampling. If a task still fails after two honest
  attempts, restore its files from the last good tag, mark it BLOCKED in
  docs/TASK_QUEUE.md, and stop. If budget runs low: commit, push, write exactly where
  you stopped in docs/TASK_QUEUE.md, and stop.
- Do ONLY the tasks named in the session prompt, then stop with a short report.
- Keep spec_hash and fetch_key stable for existing specs so old cards and caches load.
- Out of scope: progressive loading, background jobs, pre-computed summaries, float-ID
  queries, accounts, new plot types.

## TASKS
S0. Close the bypass; wall-clock budget (skip if tag done-S0 exists and verified)
- Trace the real UI path (app/ui.py -> pipeline -> validator -> chunking -> fetcher) for
  "temperature profiles in the Indian Ocean in January 2023" with the fetch spied.
  Report max_request_size at each step and every place that passes None or skips a
  check. Until the planner exists the guard is ON in every UI path; env var
  SIQVA_DISABLE_SIZE_GUARDRAIL stays the only way to disable it, with a banner and a
  card note.
- Hard wall-clock budget for foreground work (named constant, env overridable, default
  90 s) plus a per-request timeout. When exceeded: stop and return a TIMEOUT message
  saying what finished (finished monthly chunks stay cached). Never hang the session.
  Tests with a mocked slow fetch; AppTest with the fetch spied.

S1. Local float index (DONE: src/siqva/floatindex.py, scripts/build_float_index.py)

S2. Capability profiles (src/siqva/capabilities.py)
- Table-driven mapping intent -> {data_need: METADATA | SAMPLE_OK | FULL_REQUIRED,
  default_depth or None, per_profile_only, label} from the table above; read the
  current defaults in parser.py for the "keep current default" rows. Depth max 2000 dbar
  in structure checks (reuse if present). The Plot Graph cards and the query path both
  read these profiles. Tests: every intent has a profile; defaults per intent; user
  depth wins.

S3. Layered validation and planner (validator.py, new planner.py)
- Split validator into structure checks and plan_request(spec, profile, index) ->
  PlanDecision {FULL, CHUNKED, SAMPLE, REFUSE, reasons, options}. Order: METADATA ->
  overview only. Index coverage FULL: exact profile counts for the whole request and per
  monthly chunk; estimated rows = profiles x depth span x LEVELS_PER_DBAR (derive from
  cached Parquet files and fixtures, document how). FULL if it fits SIQVA_MAX_FULL_ROWS;
  CHUNKED if every monthly chunk fits, months <= SIQVA_MAX_CHUNKS and total rows <=
  SIQVA_MAX_TOTAL_ROWS; else SAMPLE if the module is SAMPLE_OK, else REFUSE. Thresholds
  are named, env overridable, documented as unmeasured conservative defaults (the
  largest cached fixture, about 59,000 rows, is a reference).
- Decide only from profile counts, same thresholds for every region. Geometric cost cap
  only as fallback when the index does not cover the request (profile_count_verified
  False, visible note).
- Basin names (Pacific/Atlantic/Indian Ocean) use the index ocean column; never invent a
  bounding box; minimal backward-compatible spec representation. Antimeridian boxes:
  SAMPLE and METADATA work; FULL keeps rejecting with working options.
- Options are structured objects (label, spec edit) that re-run through the normal path
  and update "Understood as": narrower period (from index counts), shallower layer,
  smaller region (gazetteer sub-regions), float map, bigger sample, run full (only if
  allowed). Every REFUSE has at least one working option.
- Tests: parametrized consistency (same request size in six regions incl. Pacific and an
  antimeridian box gives the same decision); each branch; fallback without index;
  options build valid specs.

S4. Metadata and overview
- Float-location questions ("show floats in the Indian Ocean", "map of floats in the
  Pacific", "how many floats/profiles in ...") are METADATA: no dates or variables
  required (default period = last 30 days before the snapshot date, shown as default),
  no fetcher call, no size check, any region incl. basins.
- Overview map from the index only: tracks within a named limit, otherwise markers at
  last position, above 5,000 floats a coarse grid of counts with Scattergeo markers (no
  tiles). Hover: float, last date, cycle, institution. Show snapshot date, age, exact
  counts. Record render time. The Float Position Map card uses this path.
- Tests: fetcher NOT called; Indian Ocean and Pacific (antimeridian) on the synthetic
  index; marker cap and grid fallback; answer text; index missing gives a clear message.

S5. Deterministic sample selection (floatindex.select_sample)
- Per design point 3; returns picks (wmo, cycle, date, lat, lon) and a method
  description. Tests: determinism, spread, distinct floats, one profile per cell/slice,
  delayed filter, antimeridian, fewer profiles than n, empty region.

S6. Fetch the sample (fetcher.py)
- Check the installed argopy for how to fetch specific profiles (state version and exact
  call). If impossible, fall back to a tiny box and a +-1 day window around each pick and
  filter to the picked cycle; log the decision. Sequential with a short pause, inside the
  S0 budget, st.status progress. One cache entry per profile (key: mode, variables, wmo,
  cycle; if the whole profile is returned cache once and clip to depth on load). Same
  QC/mode logic; effective depth = module default, shown as such. Partial failure:
  return what succeeded, flag "k of n fetched", list failures.
- FetchResult/AnalysisResult carry is_sample, n_selected, n_available, method, seed,
  index_build_date. For samples the analyzer must NOT compute region-wide statistics or
  physics summaries (per-profile display is fine).
- Tests with mocked argopy: call count equals picks, caching, partial failure, budget
  exceeded, QC applied, no regional statistics on samples.

S7. UI flow and wording (app/ui.py)
- SAMPLE shows (1) the overview map, then (2) the sample plots with the label. Buttons
  that re-run through the normal path and update "Understood as": bigger sample, smaller
  region, shorter period, float map only, run full (only when allowed). FULL/CHUNKED show
  "Full: all N profiles" (and "assembled from N monthly chunks").
- Data questions and statistic modules on a too-large region: REFUSE with the design
  sentence and options. FULL_REQUIRED modules never show a sample.
- Plain-language message per PlanDecision, no raw tracebacks. Replace the "Auto-shrink"
  button with the structured options (record changes in the card).
- AppTests with the fetch spied: Indian Ocean temperature profiles (sample path, fetch
  calls = picks, label present); Hovmoller on the same region (REFUSE with options);
  float-map request without dates/variables; bigger-sample button; small Arabian Sea
  request (FULL); partial failure; budget exceeded.

S8. Query card and script
- Card records the plan decision and, for samples, the (wmo, cycle) list, method, seed,
  index build date, counts. generate_script reproduces exactly those profiles (no index
  needed) and states in its header that it reproduces the sample, not the region.
  Re-run compares the same sample. Old cards still load. Tests incl. compile().

S9. Plot Graph page and Compare Runs
- Each "Configure & Plot" card shows its capability (Metadata / Sample allowed / Full
  data required) and applies S3. Compare Runs compares only FULL or CHUNKED runs; if a
  side would be a sample it explains why and offers options. Tests.

S10. Docs, measurements, final
- Update AGENTS.md (float index allowed for discovery, maps, counts, sampling, never
  profile values; layered validation; no-dead-ends rule; samples are never region
  statistics), README.md, docs/CODE_FLOW.md, new docs/SAMPLING.md (design, constants,
  capability table, rebuilding the index, monthly refresh, limits; thresholds are
  unmeasured defaults). scripts/review/bench_sampling.py (offline) timing index query,
  count, select_sample and overview render on a 3,000,000-row synthetic index.
- Final: pytest -q -rs, push, report per task DONE/BLOCKED with hashes, test counts,
  whether the real index was present (real column names, ocean codes), measured times,
  what was not verified (live per-profile fetch time, real browser), AGENTS.md
  conflicts, and a PR title and plain-words description.