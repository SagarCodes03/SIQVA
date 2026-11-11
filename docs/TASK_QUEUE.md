# SIQVA Task Queue

Resume instruction for future sessions:
> "Read docs/TASK_QUEUE.md and continue with the first unchecked task."

| Task | Description | Status / Notes |
| :--- | :--- | :--- |
| [x] **Q1** | Finish the Task C branch (investigate 146 profiles vs 100 cap, pytest, push task-c-parser-history, PR info, docs drift check) | DONE (commit `b801808`, 198 passed) |
| [x] **Q2** | Crash and safety fixes (SQLite closing, Ollama fast failure, HTML escaping, gsw guard in plots, DECISIONS.md entries) | DONE (commit `6c32b52`, tag `done-Q2`, 199 passed) |
| [x] **Q3** | Pacific cost messages and regions (investigate gazetteer, actionable oversized message, named Pacific sub-regions, Pacific warning) | DONE (commit `9263d22`, tag `done-Q3`, 222 passed) |
| [x] **Q4** | Cleanup and safety net (dead code in fetcher, tz-aware UTC, requirements.txt, all-module import test, AppTest smoke test, docs sync) | DONE (tag `done-Q4`, 241 passed) |
| [x] **Q3b** | Large-query chunking (calendar-month chunking under 15,000 cap, row/chunk limits, shared caching, assembly, tests) | DONE (tag `done-Q3b`, 252 passed) |
| [x] **Q5** | Operations core for data questions (OperationSpec, execute statistics, deterministic answer template, no LLM, hand-computed tests) | DONE (tag `done-Q5`, 260 passed) |
| [x] **Q8** | Glossary mechanism (glossary.py, data/glossary.json, exact/fuzzy lookup, source attribution, no definitions written, guide) | DONE (tag `done-Q8`, 268 passed) |
| [x] **Q6** | Router and chat interface (route() classifier, constrained fallback, monthly fetch/cache, st.chat_message UI, tests) | DONE (tag `done-Q6`, 283 passed) |
| [x] **Q7** | Follow-ups and meta questions (ConversationState, conversational edits, meta queries from card/state, tests) | DONE (tag `done-Q7`, 294 passed) |
| [x] **Q9** | Comparison questions (dual OperationSpecs execution, difference reporting without anomaly claims, router detection, tests) | DONE (tag `done-Q9`, 301 passed) |
| [x] **Q10** | Cold start (example gallery from JSON, non-blocking Ollama background warm-up, st.status progress stages, tests) | DONE (tag `done-Q10`, 305 passed) |
| [x] **Q11** | History reload and privacy (cache-based plot reload, session ID isolation, privacy docs/tests) | DONE (tag `done-Q11`, 308 passed) |
| [x] **Q13** | Benchmark infrastructure (benchmark/questions.jsonl, run_eval.py runner, accuracy/latency scoring, tests) | DONE (tag `done-Q13`, 310 passed) |
| [x] **Q14** | Documentation (comprehensive README.md, AGENTS.md, CODE_FLOW.md, limitations, reproducible query cards) | DONE (tag `done-Q14`, 310 passed) |
| [x] **FIX 1** | UI smoke test absolute paths (AppTest path resolution, fixture paths, realistic mocked run pipeline) | DONE (commit `53e5445`, 310 passed) |
| [x] **FIX 2** | Glossary utf-8 encoding and verification (`verified: false` default, structured `GlossarySource`, warning on unverified terms, guide checklist) | DONE (commit `6e8794d`, 311 passed) |
| [x] **FIX 3** | Honest benchmark labelling and split field (`split: dev` schema, sample size warning < 30, parser-only latency label, docs disclaimer) | DONE (commit `015f86c`, 312 passed) |
| [x] **FIX 4** | Safety verification (unquantified date clarifications, Ollama-unavailable < 3s, actionable oversized basin message, docs sync) | DONE (commit `938d3f5`, 315 passed) |
| [x] **F1** | Physics honesty (SOFAR interior requirement, MIN_SAMPLES_EACH_SIDE=3, SLD surface behavior, aggregate 'N of M' text, shallower profiles count) | DONE (tag `done-F1`, 329 passed) |
| [x] **F2** | Fetcher binding and offline-safe tests (call-time fetcher resolution, network guard in conftest) | DONE (tag `done-F2`, 335 passed) |
| [x] **F3** | Plot size (MAX_PLOT_OBSERVATIONS=5000 stratified sampling, Scattergl, sampling annotation) | DONE (tag `done-F3`, 340 passed) |
| [x] **F4** | Reproducibility honesty (reproduction scope in script header for all intents, chunked script support) | DONE (commit `8279ebe`, 366 passed) |
| [-] **F5-F6** | Guardrail visibility & measurement / cleanup | Unfinished / superseded by S0-S10 sampling design |
| [x] **S0** | Find and close the bypass; wall-clock budget (trace real UI path, enforce guard on all UI paths, foreground wall-clock budget 90s, AppTest fetch spy) | DONE (tag `done-S0`, 371 passed) |
| [x] **S1** | Local float index (src/siqva/floatindex.py, scripts/build_float_index.py, load once, query_profiles, count_profiles, last_positions, tracks, coverage_status, tests) | DONE (tag `done-S1`, 381 passed) |
| [x] **S2** | Capability profiles (src/siqva/capabilities.py table mapping intent -> METADATA / SAMPLE_OK / FULL_REQUIRED, default depths, 2000 dbar cap, tests) | DONE (tag `done-S2`, 385 passed) |
| [x] **S3** | Layered validation and planner (validator.py, planner.py, PlanDecision, basin support, antimeridian, structured options, tests) | DONE (tag `done-S3`, 400 passed) |
| [x] **S4** | Metadata and overview (router/rules parser, pipeline, plots, float-location queries, index overview map, Scattergeo, tests) | DONE (tag `done-S4`, 406 passed) |
| [x] **S5** | Deterministic sample selection (floatindex.select_sample, WMO+cycle, grid x time slices, distinct floats, seed from fetch_key + build_date, tests) | DONE (tag `done-S5`, 420 passed) |
| [x] **S6** | Fetch the sample (fetcher.py per-profile fetch, caching, progress, partial failure handling, FetchResult/AnalysisResult metadata, tests) | DONE (tag `done-S6`, 427 passed) |
| [x] **S7** | UI flow and wording (app/ui.py overview map + sample plots, label, interactive options buttons, plain-language PlanDecision, AppTests) | DONE (tag `done-S7`, 446 passed) |
| [x] **S8** | Query card and script (card records plan decision, sample profile list, honest sample script generation, rerun, tests) | DONE (tag `done-S8`, 451 passed) |
| [x] **S9** | Plot Graph page and Compare Runs (capability display, S3 plan enforcement, Compare Runs FULL/CHUNKED restriction, tests) | DONE (tag `done-S9`, 454 passed) |
| [ ] **S10** | Docs, measurements, final (AGENTS.md, README.md, CODE_FLOW.md, docs/SAMPLING.md, bench_sampling.py offline benchmarks, final report) | PENDING |
