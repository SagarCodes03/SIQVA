# SIQVA: Read-Only Baseline Analysis & Current State

**Branch**: `analysis-baseline`  
**Date**: 2026-11-10  
**Environment**: Python 3.11, Windows  
**Status**: Section 1 and Section 2 complete. Next section: Section 3.

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


---

## SECTION 2: The Request-Size Limit (Change A)

### 2.1 The Area × Days × Depth Cost Cap: Definition, Enforcement & Collaborator Changes

1. **Existence & Definition**:
   - The cost cap formula ($\text{Area} \times \text{Days} \times [\text{Depth Span} / 500\text{ dbar}]$) still exists.
   - It is defined in [`src/siqva/validator.py:12`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/validator.py#L12):
     ```python
     DEFAULT_MAX_REQUEST_SIZE: float = 15_000.0
     ```
2. **Where Enforced in Code**:
   - [`src/siqva/validator.py:165-172`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/validator.py#L165-L172): `validate_spec` computes `cost = area * days * depth_factor` and checks `if is_size_guardrail_enabled() and max_request_size is not None and cost > max_request_size:`.
   - [`src/siqva/chunking.py:100-112`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/chunking.py#L100-L112): `is_chunked_spec` checks whether `cost > max_request_size`.
   - [`src/siqva/chunking.py:133-148`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/chunking.py#L133-L148): `validate_chunkable_spec` checks whether individual monthly chunk costs exceed `max_request_size`.
   - [`src/siqva/fetcher.py:728`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L728): `fetch` verifies `if is_size_guardrail_enabled() and max_request_size is not None and not is_chunked and cost > max_request_size:`.
   - [`src/siqva/pipeline.py:80, 260`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/pipeline.py#L80): Propagates `max_request_size` to validator and chunking.
   - [`app/ui.py:866`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L866): `_ui_max_request_size()` returns `DEFAULT_MAX_REQUEST_SIZE`.

3. **Comparison with Tag `done-Q14` (`git diff done-Q14 HEAD`)**:
   - **Did the collaborator raise the cap?** No. The numerical constant remains `15_000.0`.
   - **Did the collaborator remove the cap?** No. The formula and exception `OversizedRequestError` remain in place.
   - **What the collaborator changed (Bypassed & Made Optional)**:
     1. *Bypass Hook Added*: In [`src/siqva/validator.py:15-21`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/validator.py#L15-L21), added `is_size_guardrail_enabled()`, which checks `os.getenv("SIQVA_DISABLE_SIZE_GUARDRAIL", "").lower() not in ("1", "true", "yes")`. If set, all size checks evaluate to `False`.
     2. *Optional Argument Signature*: Changed parameter `max_request_size: float = DEFAULT_MAX_REQUEST_SIZE` to `Optional[float]` across `validator.py`, `chunking.py`, `fetcher.py`, and `pipeline.py`. When passed `max_request_size=None`, validation and chunking bypass the check.
     3. *Chunking Bypass*: In [`src/siqva/chunking.py:106`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/chunking.py#L106), added `if max_request_size is None or not is_size_guardrail_enabled(): return True`, unconditionally allowing multi-month chunking.
     4. *UI Clamping Button*: In [`app/ui.py:922`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L922), added an "Auto-shrink Query to Fit Cost Limit & Re-run" button when `PipelineStatus.OVERSIZED` is returned.

---

### 2.2 Other Operational Limits & Environment Variables

| Limit Type | Constant Name | Default Value | Environment Variable | Defined Location |
|---|---|---|---|---|
| Single-Request Cost Cap | `DEFAULT_MAX_REQUEST_SIZE` | `15_000.0` cost units | `SIQVA_DISABLE_SIZE_GUARDRAIL=1` (to bypass) | [`validator.py:12`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/validator.py#L12) |
| Maximum Monthly Chunks | `DEFAULT_MAX_CHUNKS` | `24` chunks (months) | `SIQVA_MAX_CHUNKS` | [`chunking.py:27, 33`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/chunking.py#L27) |
| Maximum Combined Rows | `DEFAULT_MAX_TOTAL_ROWS` | `3,000,000` rows | `SIQVA_MAX_TOTAL_ROWS` | [`chunking.py:28, 44`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/chunking.py#L28) |
| Pre-Fetch Profile Ceiling | `DEFAULT_MAX_PROFILE_COUNT` | `100` profiles | None | [`fetcher.py:38`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L38) |
| Cache Expiration (Standard/Expert) | `DEFAULT_CACHE_EXPIRY_DAYS` | `7` days | None | [`fetcher.py:31`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L31) |
| Cache Expiration (Research) | `DEFAULT_RESEARCH_CACHE_EXPIRY_DAYS` | `90` days (immutable by hash) | None | [`fetcher.py:32`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L32) |
| Data Fetch Network Timeout | `timeout` | `60` seconds | None | [`fetcher.py:325, 592`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L325) |
| Remote Index Network Timeout | `timeout` | `30` seconds | None | [`fetcher.py:441`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L441) |
| Profile Display Plot Cap | `max_profiles` | `25` profiles | None | [`plots.py:68, 120`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/plots.py#L68) |
| History Isolation Mode | `SIQVA_SHARED_HISTORY` | `1` (shared) | `SIQVA_SHARED_HISTORY=0` (isolated) | [`card.py:338`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/card.py#L338) |

---

### 2.3 The "Auto-Shrink" Button

- **Location**: [`app/ui.py:920-950`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L920-L950)
- **Trigger**: Appears exclusively when a query fails with `PipelineStatus.OVERSIZED`.
- **Exact Behavior**:
  1. *If Intent is Map or Drift*:
     Clamps `depth_range` to `DepthRange(min_depth=0.0, max_depth=20.0)` while keeping the user's dates and region intact ([`app/ui.py:924-927`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L924-L927)).
  2. *For All Other Intents (Profile, T-S, Physics, etc.)*:
     - Computes the bounding box area: `area = (lon_max - lon_min) * (lat_max - lat_min)`.
     - Computes depth factor: `depth_factor = cur_span / 500.0`.
     - Computes daily cost: `cost_per_day = area * depth_factor`.
     - Calculates maximum fitting days: `max_fitting_days = int(15_000.0 / cost_per_day)`.
     - Arbitrarily caps maximum allowed duration to **14 days**: `clamped_days = min(max_fitting_days, 14)` ([`app/ui.py:936`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L936)).
     - Sets new end date: `new_end = start + timedelta(days=clamped_days)`.
     - Re-executes the pipeline with `run_spec(clamped_spec)` and calls `st.rerun()`.

---

### 2.4 Float Map: Data Fetching, Observations & Columns

1. **Which Fetch Runs When Intent is "map"?**:
   - `pipeline.run_spec` executes [`src/siqva/pipeline.py:96`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/pipeline.py#L96), which calls `fetcher.fetch()`.
   - `fetcher.fetch()` instantiates [`src/siqva/fetcher.py:791`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L791):
     ```python
     engine = argopy.DataFetcher(mode=mode_str, src=src, api_timeout=timeout)
     fetch_ds = engine.region(box)
     ```
   - **It downloads FULL physical observations** (all vertical measurement levels, temperature, salinity, pressure, QC flags, and error bars) over ERDDAP.
2. **Which Columns Does `plot_position_map` Really Use?**:
   - Defined in [`src/siqva/plots.py:264-340`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/plots.py#L264-L340).
   - Only reads:
     - `LATITUDE` (or `latitude`)
     - `LONGITUDE` (or `longitude`)
     - `PLATFORM_NUMBER` (WMO float identifier)
     - `CYCLE_NUMBER` (profile cycle)
     - `TIME` (for chronological trajectory sorting)
   - It groups by `PLATFORM_NUMBER`, drops duplicates on `CYCLE_NUMBER`, and plots a `Scattergeo` trajectory.
   - **It never uses `TEMP`, `PSAL`, `PRES`, or any observation values.**
3. **Is There Any Code Path That Gets Float Positions Without Observations?**:
   - **No.** There is zero runtime code in SIQVA that fetches positions without downloading full observation profiles.
   - `argopy.IndexFetcher` exists in `fetcher.py:340, 444`, but it is only used in offline snapshot creation or remote count fallback. It is never used to populate the map.

---

### 2.5 Float Index: Inventory, Usage & Dead Code

1. **What Exists?**:
   - Function `create_float_index_snapshot(...)` in [`src/siqva/fetcher.py:320-438`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L320-L438).
   - Sidecar evaluator `get_snapshot_coverage_status(...)` in [`src/siqva/fetcher.py:165-215`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L165-L215).
   - Profile counter `count_profiles_in_snapshot(...)` in [`src/siqva/fetcher.py:220-315`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L220-L315).
2. **Does `data/float_index.parquet` Exist? Size & Coverage**:
   - File exists on disk: `data/float_index.parquet` (file size: **3,521 bytes**).
   - Read from sidecar [`data/float_index.json`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/data/float_index.json):
     ```json
     {
       "fetch_date": "2026-10-22T15:22:35.133613Z",
       "bbox": [-30.0, -28.0, 32.0, 34.0],
       "min_date": "2022-01-01",
       "max_date": "2022-01-10",
       "row_count": 2,
       "source": "argopy.IndexFetcher snapshot"
     }
     ```
   - It covers only **2 rows** in a 2°×2° patch of the North Atlantic across 10 days in 2022.
3. **Which Code Uses It? What is Dead?**:
   - In [`src/siqva/pipeline.py:96`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/pipeline.py#L96), `run_spec` calls `fetcher_fn(spec, ...)` without passing `float_index_path`.
   - In [`src/siqva/fetcher.py:598`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L598), parameter `float_index_path: Optional[Path | str] = None` defaults to `None`.
   - In `fetcher.py:702`: `if float_index_path is not None:`
   - Because `float_index_path` is never passed by the pipeline or UI, **the float index is 100% dead code during live user runs**.
   - Only test files (`tests/test_fetcher.py`) pass `float_index_path` explicitly.
4. **Does `data/raw/` Exist, and Does It Hold `ar_index_global_prof.txt.gz`?**:
   - **No.** `Test-Path data/raw` returns `False`. The directory does not exist and no GDAC global index file is present.

---

### 2.6 Reproduction of User Complaints (Real Path: Route -> Parse -> Validate -> Pipeline with Mocked Fetch)

Executed offline via Python script importing real modules:

#### a) "show floats in the Indian Ocean"
- **Route**: `RouteTarget.DATA_FETCH` (confidence 0.8)
- **Parsed Spec**: `None`
- **Cause**: Parser missing required fields (`date_range`, `variables`).
- **Exact User Message**:
  > *"The language model is not available. Missing required fields: date_range, variables. Please specify the missing parameters or fill them in the spec panel. Please specify a time period (e.g. 'in year 2021' or '2022-01-01 to 2022-01-10'). Please specify ocean variables to measure (e.g. 'temperature', 'salinity', 'pressure'). You can manually configure missing parameters in the spec panel."*
- **Actionability / Dead End**: **Dead end**. The user only asked to view float positions, but the pipeline requires time ranges and measurement variables (TEMP, PSAL) because it insists on downloading observation data.

#### b) "map of floats in the Pacific Ocean"
- **Route**: `RouteTarget.DATA_FETCH` (confidence 0.8)
- **Parsed Spec**: `None`
- **Cause**: Gazetteer Pacific Ocean guard ([`gazetteer.py:330-350`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/gazetteer.py#L330-L350)) + missing dates/variables.
- **Exact User Message**:
  > *"The language model is not available. Missing required fields: date_range, variables. Please specify the missing parameters or fill them in the spec panel. The Pacific Ocean as a whole is too large for one query and crosses the 180° meridian. Supported Pacific regions: Eastern equatorial Pacific, Nino 3.4, Nino 3, Nino 1+2. Or provide coordinates like '5S-5N, 170W-120W'. Please specify a time period (e.g. 'in year 2021' or '2022-01-01 to 2022-01-10'). Please specify ocean variables to measure (e.g. 'temperature', 'salinity', 'pressure'). You can manually configure missing parameters in the spec panel."*
- **Actionability / Dead End**: **Dead end for the Pacific basin**. The whole Pacific Ocean cannot be resolved.

#### c) "temperature profiles in the Pacific Ocean in 2023"
- **Route**: `RouteTarget.DATA_FETCH` (confidence 0.8)
- **Parsed Spec**: `None`
- **Cause**: Gazetteer Pacific Ocean guard ([`gazetteer.py:330-350`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/gazetteer.py#L330-L350)).
- **Exact User Message**:
  > *"The language model is not available. Please specify the missing parameters or fill them in the spec panel. The Pacific Ocean as a whole is too large for one query and crosses the 180° meridian. Supported Pacific regions: Eastern equatorial Pacific, Nino 3.4, Nino 3, Nino 1+2. Or provide coordinates like '5S-5N, 170W-120W'. You can manually configure missing parameters in the spec panel."*
- **Actionability / Dead End**: Offers 4 sub-regions, but querying the Pacific Ocean basin as a whole remains a hard rejection.

#### d) "temperature profiles in the Indian Ocean in January 2023"
- **Route**: `RouteTarget.DATA_FETCH` (confidence 0.8)
- **Parsed Spec**: `None` (validator raised `OversizedRequestError` inside `parse_detailed`)
- **Cause**: Cost Cap Guard ([`validator.py:165-200`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/validator.py#L165-L200)).
  - Indian Ocean area = $100^\circ \times 75^\circ = 7,500^\circ{}^2$.
  - 30 days at default 500 dbar depth span = $7,500 \times 30 \times 1.0 = 225,000$ cost units.
  - $225,000 > 15,000$ cap. Because January 2023 is a single calendar month, chunking cannot partition it.
- **Exact User Message**:
  > *"Request exceeds allowable size cap (225000 > 15000 cost units). Request volume (225,000.0 cost units) exceeds the maximum limit (15,000.0). Current region 'Indian Ocean' (7,500.0°²) across 30 days with depth range 0–500 dbar (span 500 dbar). At this depth range, at most 2 days fit under the limit. Please narrow your query with one of the following: 1. Shorter period: narrowing the date range to 2 days or fewer (e.g. at most 2 days at this depth). 2. Shallower depth: choosing a shallower depth range with a span of at most 33 dbar (e.g. 0–33 dbar) for 30 days. 3. Smaller region: shrinking the bounding box or specifying precise coordinates to reduce the area from 7,500.0°²."*
- **Actionability / Dead End**: **Dead end in practice**. Suggesting "at most 2 days" or "0–33 dbar" across the entire Indian Ocean is useless for physical oceanography.

#### e) "temperature profiles in the Arabian Sea in 2024" (Multi-Month)
- **Route**: `RouteTarget.DATA_FETCH` (confidence 0.8)
- **Parsed Spec**: Validated successfully:
  - Region: `[50.0, 77.0, 8.0, 25.0]` (Arabian Sea, Area = 459°²)
  - Date: `2024-01-01` to `2024-12-31`
  - Variables: `[TEMP]`
  - Depth: `0–500 dbar`
- **Cause**: Multi-month chunking succeeds!
  - Monthly cost = $459 \times 31 \times 1.0 = 14,229 \le 15,000$ units.
  - Decomposed into 12 monthly chunks under the cap.
- **Pipeline Status**: `SUCCESS`
- **User Message**: Rendered successfully.

---

### 2.7 Gazetteer: KNOWN_REGIONS & Basin Definitions

Defined in [`src/siqva/gazetteer.py:39-65`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/gazetteer.py#L39-L65):

| Region Name | Longitude Min | Longitude Max | Latitude Min | Latitude Max | Area (deg²) |
|---|---|---|---|---|---|
| **Arabian Sea** | 50.0 | 77.0 | 8.0 | 25.0 | 459.0 |
| **Bay of Bengal** | 80.0 | 100.0 | 5.0 | 22.5 | 350.0 |
| **Indian Ocean** | 20.0 | 120.0 | -50.0 | 25.0 | 7,500.0 |
| **Eastern equatorial Pacific** | -170.0 | -80.0 | -10.0 | 10.0 | 1,800.0 |
| **North Atlantic** | -80.0 | 0.0 | 0.0 | 65.0 | 5,200.0 |
| **Mediterranean Sea** | -6.0 | 36.0 | 30.0 | 46.0 | 672.0 |
| **Nino 1+2** | -90.0 | -80.0 | -10.0 | 0.0 | 100.0 |
| **Nino 3** | -150.0 | -90.0 | -5.0 | 5.0 | 600.0 |
| **Nino 3.4** | -170.0 | -120.0 | -5.0 | 5.0 | 500.0 |

- **Does "Indian Ocean" have a box?**: **Yes**. Bounding box is `[20.0, 120.0, -50.0, 25.0]` (Area: 7,500 deg²).
- **Which basin names are known?**:
  - `Indian Ocean` (resolved to the 7,500 deg² box).
  - `North Atlantic` (resolved to the 5,200 deg² box).
  - `Pacific Ocean` has **no bounding box** in `KNOWN_REGIONS`. Queries matching "Pacific Ocean" are intercepted by a dedicated guard in `gazetteer.py:330-350` and returned as `UNKNOWN` with a clarification message.
