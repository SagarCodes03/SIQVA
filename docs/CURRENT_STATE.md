# SIQVA: Read-Only Baseline Analysis & Current State

**Branch**: `analysis-baseline`  
**Date**: 2026-11-10  
**Environment**: Python 3.11, Windows  
**Status**: Section 1 complete. Next section: Section 2.

---

## SECTION 1: Where the Project Stands

### 1.1 Git Branch, Commits & Tags

- **Current Branch**: `analysis-baseline` (verified via `git status`).
- **Branch Inclusion**:
  - Contains `origin/main` (`ba4d149`): **Yes**. Verified with `git branch -a --contains ba4d149` and `git merge-base HEAD origin/main` returning `ba4d149`.
  - Contains `origin/siqva-finish` (`9db4582`): **Yes**. Merged in commit `864ac91`. Verified with `git merge-base HEAD origin/siqva-finish` returning `9db4582`.
  - Specifically checked commits:
    - `3e5990f` (Sangeen: extended plots and terminal): **Contained in HEAD**.
    - `d625a03` (Sangeen: surface depth default, auto-shrink button): **Contained in HEAD**.
    - `ba4d149` (Sangeen: Release v0.9): **Contained in HEAD**.
- **Uncommitted Changes**:
  - No modified tracked files. Untracked review files only in `scripts/review/`.
- **Existing Tags**:
  - `done-FIX1`, `done-FIX2`, `done-FIX3`, `done-FIX4`, `done-Q10`, `done-Q11`, `done-Q13`, `done-Q14`, `done-Q2`, `done-Q3`, `done-Q3b`, `done-Q4`, `done-Q5`, `done-Q6`, `done-Q7`, `done-Q8`, `done-Q9`, `pre-siqva-rename`, `v0.9`.
- **Last 15 Commits with Author**:
  1. `2a54ea4` | Sagar Gowda H | 2026-11-09 | review: phase 0 inventory
  2. `864ac91` | Sagar Gowda H | 2026-11-09 | Merge remote-tracking branch origin/siqva-finish
  3. `ba4d149` | Sangeen | 2026-11-09 | Release v0.9: Enterprise minimalist UI overhaul, multi-year query support, and modal date fixes
  4. `d625a03` | Sangeen | 2026-11-08 | fix(ui): surface depth default for map intent, auto-shrink button, and sidebar layout aesthetics
  5. `f168d13` | Sangeen | 2026-11-08 | Merge branch 'feature/ui-updates' into main
  6. `9db4582` | Sagar Gowda H | 2026-11-07 | docs: update task queue with completed fixes
  7. `938d3f5` | Sagar Gowda H | 2026-11-07 | Docs and safety verification
  8. `015f86c` | Sagar Gowda H | 2026-11-07 | Honest benchmark labelling and split field
  9. `6e8794d` | Sagar Gowda H | 2026-11-07 | Glossary: utf-8 loading, verified flag
  10. `53e5445` | Sagar Gowda H | 2026-11-07 | Fix UI smoke test paths
  11. `164e761` | Sagar Gowda H | 2026-11-07 | Merge pull request #9 from SagarCodes03/siqva-finish
  12. `6f1bf3b` | Sagar Gowda H | 2026-11-07 | docs: comprehensive README with architecture, setup, capabilities, and limitations (Q14)
  13. `940239a` | Sagar Gowda H | 2026-11-07 | feat: benchmark evaluation infrastructure and questions dataset (Q13)
  14. `dd7795c` | Sagar Gowda H | 2026-11-07 | feat: history cache reload with plot restoration and session privacy isolation (Q11)
  15. `3e5990f` | Sangeen | 2026-11-07 | feat(ui): add extended oceanographic plots and interactive terminal features

---

### 1.2 Module Inventory & Tracked Junk Files

Line counts computed strictly by line-counting script:

#### Source Modules (`src/siqva/`)
| Module | Line Count | Purpose |
|---|---|---|
| `src/siqva/__init__.py` | 123 | Public package exports |
| `src/siqva/analyzer.py` | 542 | Deterministic coverage & statistical metrics |
| `src/siqva/card.py` | 625 | QueryCard builder, SQLite storage, script generator |
| `src/siqva/chunking.py` | 362 | Calendar-month partitioning for multi-month queries |
| `src/siqva/comparison.py` | 110 | Dual-entity difference reporting |
| `src/siqva/fetcher.py` | 917 | argopy data access, caching, and profile index counting |
| `src/siqva/followup.py` | 141 | Conversational follow-up query resolution |
| `src/siqva/gazetteer.py` | 474 | Geographic gazetteer and fuzzy coordinate resolution |
| `src/siqva/glossary.py` | 201 | Oceanographic terminology lookup from JSON |
| `src/siqva/interpretation.py` | 56 | Deterministic formatting of interpreted fields |
| `src/siqva/llm_parser.py` | 454 | Ollama fallback parser for unfilled fields |
| `src/siqva/operations.py` | 235 | Statistical numerical operations on Argo observations |
| `src/siqva/parser.py` | 385 | Orchestrator (rules -> LLM -> validator fallback) |
| `src/siqva/physics.py` | 452 | TEOS-10 thermodynamics & acoustics (gsw) |
| `src/siqva/pipeline.py` | 292 | End-to-end execution pipeline |
| `src/siqva/plots.py` | 1,574 | Plotly visualization templates (13 figure types) |
| `src/siqva/qc.py` | 238 | Quality Control auditing and filtering |
| `src/siqva/router.py` | 147 | Intent classification router |
| `src/siqva/rules_parser.py` | 718 | Deterministic regex/dictionary parser |
| `src/siqva/spec.py` | 223 | Pydantic QuerySpec and data structures |
| `src/siqva/validator.py` | 203 | Domain constraints and cost-cap validation |

#### Application & Evaluation Modules
| Module | Line Count | Purpose |
|---|---|---|
| `app/ui.py` | 1,781 | Active Streamlit user interface |
| `benchmark/run_eval.py` | 255 | Developer benchmark harness |

#### Tracked Junk Files
| File | Line Count | Size | Status in Codebase |
|---|---|---|---|
| `old_ui_0.1.py` | 1,651 | 73,279 bytes | **Tracked dead backup**. Verified: zero imports across the entire repository (`git grep "old_ui"` returns only docs). |
| `app/old_ui.py` | 690 | 27,540 bytes | **Tracked dead backup**. Verified: zero imports across the entire repository. |

---

### 1.3 Test Suite Status

Executed via background pytest command with `faulthandler_timeout=60` and `--durations=10`:
- **Total Tests Collected**: 329
- **Passed**: 324
- **Skipped**: 4
- **Deselected (Hanging Offline)**: 1 (`tests/test_ui_smoke.py::test_ui_runs_rules_only_query_against_mock_fetcher`)
- **Warnings**: 1 (`RuntimeWarning: divide by zero encountered in divide` in `gsw/stability.py:86` during buoyancy test)
- **Duration**: 48.82s

#### Every Skip with Reason
1. `tests/test_card.py:356` (`test_live_check_card_and_script`):
   *Reason*: `"Network test: skipped by default, set RUN_NETWORK_TESTS=1 to run"`
2. `tests/test_fetcher.py:771` (`test_network_tiny_real_fetch`):
   *Reason*: `"Network test hitting remote ERDDAP skipped by default. Set RUN_NETWORK_TESTS=1 to run."`
3. `tests/test_llm_parser.py:89` (`test_live_ollama_intent_extraction`):
   *Reason*: `"Requires live Ollama server; run with RUN_OLLAMA_TESTS=1"`
4. `tests/test_physics.py:249` (`test_4_live_argopy_smoke_test`):
   *Reason*: `"Live network test skipped by default. Set RUN_NETWORK_TESTS=1 to run."`

#### The 10 Slowest Tests
1. `0.71s` (setup): `tests/test_analyzer.py::test_analyze_computes_deterministic_statistics`
2. `0.62s` (call): `tests/test_history_reload.py::test_restore_card_result_with_cached_parquet`
3. `0.20s` (call): `tests/test_physics.py::test_each_physics_intent_calls_only_its_own_calculation_group`
4. `0.16s` (call): `tests/test_physics.py::test_standard_intents_do_not_call_compute_new_features`
5. `0.09s` (call): `tests/test_benchmark.py::test_run_benchmark_evaluation_and_split_reporting`
6. `0.09s` (call): `tests/test_fetcher.py::test_cache_expiry_research_mode_never_expires_unless_argopy_version_changes`
7. `0.09s` (call): `tests/test_fetcher.py::test_cache_expiry_standard_and_expert_modes`
8. `0.08s` (call): `tests/test_pipeline.py::test_pipeline_run_spec_success`
9. `0.08s` (call): `tests/test_pipeline.py::test_pipeline_save_card_failure_survives_with_warning`
10. `0.08s` (call): `tests/test_ui_smoke.py::test_ui_starts_without_exception`

#### Test Hanging Offline
- **Test ID**: `tests/test_ui_smoke.py::test_ui_runs_rules_only_query_against_mock_fetcher`
- **Root Cause Verified via Faulthandler Traceback**: In `tests/test_ui_smoke.py:53`, the test applies `with patch("siqva.pipeline.fetch", return_value=sample_fetch_result):`. However, `pipeline.run` defines `def run(..., fetcher_fn=fetch):` where default argument `fetch` was evaluated at module import time to `siqva.fetcher.fetch`. Because `app/ui.py:1618` calls `run(question)` without passing `fetcher_fn`, Python invokes the unpatched `siqva.fetcher.fetch`. That initiates a live `argopy.DataFetcher("erddap")` call which hangs indefinitely in `socket.accept()` / `socketpair()` and `fsspec.implementations.http` when offline.

---

### 1.4 Does the App Start?

- **Verification**: `tests/test_ui_smoke.py::test_ui_starts_without_exception` PASSED in 0.08s.
- Uses `streamlit.testing.v1.AppTest.from_file("app/ui.py")` with a 30s timeout.
- Output: 0 unhandled exceptions; loads layout, sidebar, session state, and terminal header cleanly.

---

### 1.5 The 10 Most Important Outdated or False Statements in README / AGENTS.md

1. **Intents Scope (`AGENTS.md` §7, `README.md` §4)**: Both claim SIQVA supports only 7 intents (`profile`, `map`, `ts`, `trend`, `thermocline`, `tchp`, `acoustic`).
   *Reality*: Commit `3e5990f` added 6 new intents in `src/siqva/spec.py:41-46`: `HOVMOLLER`, `BUOYANCY`, `TS_ISOPYCNAL`, `CLIMATOLOGY`, `OMZ`, and `DRIFT` (13 total).
2. **Prohibition of Biogeochemical / BGC Scope (`AGENTS.md` §3, `README.md` §6)**: Both explicitly state "Do NOT build: BGC or Deep Argo support (post-MVP)" and "Core Argo Depth Scope: Core physical variables (TEMP, PSAL, PRES)... Biogeochemical (BGC) is post-MVP scope."
   *Reality*: `Variable.DOXY` was added to `Variable` enum (`src/siqva/spec.py:20`), "oxygen"/"doxy" was added to synonyms (`src/siqva/rules_parser.py:55-56`), and `plot_bgc_omz_profile` was introduced (`src/siqva/plots.py:1260`).
3. **Hard 15,000 Cost Cap (`AGENTS.md` §7, `README.md` §4)**: Claims: "Single-Request Cost Cap: Automatically enforces a 15,000 cost-unit cap".
   *Reality*: `src/siqva/validator.py:15-18` now allows complete bypassing of the cost cap via `os.environ["SIQVA_DISABLE_SIZE_GUARDRAIL"] = "1"`, and `max_request_size` can be passed as `None`. Furthermore, `app/ui.py:922` adds an "Auto-shrink" button, and `app/ui.py:1522` allows queries to bypass or clamp.
4. **Uniform 0–500 dbar Depth Default (`AGENTS.md` §7, `README.md` §4)**: State or imply default depth is always `0–500 dbar` (`depth_span / 500.0`).
   *Reality*: Commit `d625a03` modified `src/siqva/parser.py:265-267` so that if `intent` is `Intent.MAP` or `Intent.DRIFT`, the default depth is overridden to `0–20.0 dbar`, NOT 500 dbar.
5. **Float Index Snapshot Active in Pipeline (`README.md` §6 Limitation 4, `CODE_FLOW.md`)**: Claims: "Pre-fetch profile count ceilings strictly apply when the local index snapshot (`data/float_index.parquet`) provides full coverage; for partial or uncovered regions, the geometric cost cap guards the query".
   *Reality*: `src/siqva/pipeline.py:96` never passes `float_index_path` to `fetch()`. In `fetcher.py:598`, `float_index_path` defaults to `None`. Snapshot checking is **completely dead in real queries**.
6. **Local Float Index File Coverage (`README.md` §6)**: Implies `data/float_index.parquet` is an active discovery tool.
   *Reality*: `data/float_index.parquet` is only 3.5 KB and holds exactly 2 rows covering a 2°×2° area in the North Atlantic for 10 days in January 2022 (`data/float_index.json:3-10`). It is useless for all real queries.
7. **Physics Calculations Restricted to 3 Intents (`AGENTS.md` §7)**: Claims "Physics runs *only* on those three intents (`thermocline`, `tchp`, `acoustic`); standard queries skip all physics calculations".
   *Reality*: `BUOYANCY` and `TS_ISOPYCNAL` intents also trigger TEOS-10 physics calculations (`gsw.Nsquared`, `gsw.sigma0`) in `rules_parser.py:695-696` and `plots.py:1020-1180`.
8. **Reproducible Script Generation for All Supported Intents (`AGENTS.md` §8, `README.md` §5)**: Claims every query generates a runnable reproduction script.
   *Reality*: `src/siqva/card.py:465-495` only generates code for the original 7 intents. The 6 new intents (`HOVMOLLER`, `BUOYANCY`, `TS_ISOPYCNAL`, `CLIMATOLOGY`, `OMZ`, `DRIFT`) produce incomplete scripts lacking their specialized plotting routines.
9. **UI Scope & Minimalist Architecture (`AGENTS.md` §3, §4)**: Architecture specifies a straightforward Streamlit query interface.
   *Reality*: `app/ui.py` grew into a 1,781-line "Oceanic Retro-Terminal" interface featuring custom CSS injections, terminal headers, modal dialogs (`@st.dialog`), and a multi-tab visual parameter editor.
10. **Test Counts (`TASK_QUEUE.md` FIX 4, `README.md`)**: Documentation records "315 passed".
    *Reality*: The test suite currently has 324 passed tests, 4 skipped, 1 deselected, and 1 runtime warning (9 tests added in recent commits).
