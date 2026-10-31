# SIQVA Codebase Audit Report
**Date**: October 31, 2026  
**Auditor**: Antigravity Assistant (Google DeepMind Advanced Agentic Coding)  
**Project**: SIQVA (Smart Interface of Query and Visualization of Argo data)  
**Environment**: Python 3.11, Windows, argopy 1.4.0, xarray 2025.9.0, pytest 9.1.1  
**Audit Scope**: Read-only verification of architecture, contracts, safety, performance, test coverage, and documentation.

---

## 1. Executive Summary

SIQVA is functionally robust, with 166 passing unit tests (4 skipped: live network/Ollama checks) and clean separation between query parsing, data fetching, QC auditing, oceanographic analysis, and Plotly visualization. The core promise—**the LLM never sees profile data values**—is strictly preserved: the LLM is only invoked with the user query string to extract search parameters, and all statistics and plots are generated deterministically. 

**The 5 Biggest Risks:**
1. **Unclosed SQLite connections** in `src/siqva/card.py` leak database handles, causing Windows file-locking errors (`PermissionError [WinError 32]` / `OperationalError: database is locked`) and potential application crashes on subsequent runs.
2. **Antimeridian bounding box queries** (`lon_min > lon_max`, such as Pacific regions crossing 180°) are unconditionally rejected by `src/siqva/validator.py`, making Pacific basin queries fail.
3. **Hard-coded Indian Ocean water-mass heuristics** in `src/siqva/physics.py` misclassify profiles anywhere else on Earth (e.g. North Atlantic or Pacific) as Indian Ocean water masses.
4. **Ollama connection timeout hang**: If the Ollama server is offline, socket connection attempts hang for 21 seconds per call, causing the hybrid parser to freeze the UI for up to **105 seconds** across 5 sequential extraction attempts.
5. **Raw HTML injection risk** in `app/ui.py`, where unescaped clarification messages are rendered inside `unsafe_allow_html=True` divs.

**The 3 Biggest Slowdowns:**
1. **Ollama socket timeout (up to 105 s)** when the Ollama service is stopped.
2. **Library import overhead (3.09 s cold start)**, dominated by eager imports of `argopy` (1.95 s) and `pandas` (0.84 s).
3. **Redundant Plotly rendering and SQLite scans** on every Streamlit click due to the complete absence of `@st.cache_data`.

---

## 2. Findings Table

Findings are classified by severity:
- **High**: Wrong or unsafe results, broken architectural contract, or an unhandled crash a normal user will hit.
- **Medium**: Degraded user experience, unhandled edge cases, or potential failure under specific conditions.
- **Low**: Code cleanup, documentation fixes, or minor technical debt.

| ID | Area | File:Line | Issue in Plain Words | User Impact | Likelihood | Suggested Fix | Effort |
|---|---|---|---|---|---|---|---|
| **F-01** | **Safety / Persistence** | [`src/siqva/card.py:229-247`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/card.py#L229-L247) | In Python's `sqlite3`, using `with sqlite3.connect(...) as conn:` manages database transactions, but **never closes the connection**. Connections remain open until garbage collection. | On Windows, open SQLite handles lock the file, causing `PermissionError: [WinError 32]` or `sqlite3.OperationalError: database is locked`. In `pipeline.py:155`, `save_card` has no `try/except`, so a lock crashes the entire pipeline even after data was successfully fetched. | **High** (frequent on Windows) | Wrap SQLite operations in `with sqlite3.connect(...) as conn:` followed by an explicit `try ... finally: conn.close()`. | Small |
| **F-02** | **Validation / Bounds** | [`src/siqva/validator.py:66-69`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/validator.py#L66-L69) | `validator.py` strictly checks `if bbox.lon_min > bbox.lon_max:` and raises `SpecValidationError`. | Queries crossing the antimeridian (180° meridian, e.g. Fiji, Chukchi Sea, New Zealand-Samoa where longitude wraps from 170° to -170°) are rejected as invalid. | **High** (for any Pacific query crossing 180°) | Allow antimeridian crossing or normalize longitude coordinates to 0..360° before dispatching to argopy. | Medium |
| **F-03** | **Scientific Physics** | [`src/siqva/physics.py:260-270`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/physics.py#L260-L270) | The water-mass heuristic classification uses hard-coded rules specifically written for the Indian Ocean (Arabian Sea High Salinity Water, Bay of Bengal Plume). | Any profile fetched from the North Atlantic, Mediterranean, or Pacific will be misclassified as "Southern Indian Ocean Water" or "Equatorial / Transitional Indian Ocean Water". | **High** (scientific misrepresentation) | Add a geographic bounding box check; if the profile is outside the Indian Ocean, label it as "Unclassified / Outside Indian Ocean Domain". | Small |
| **F-04** | **Performance / UX** | [`src/siqva/llm_parser.py:53, 67-74`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/llm_parser.py#L53-L74) | `OllamaClient` does not specify an HTTP/socket connection timeout. When the Ollama daemon is offline, Windows waits the full OS TCP timeout (21.0 seconds) per attempt. | The hybrid parser sequentially invokes up to 5 fallback functions (`extract_region_name`, `extract_date_range`, `extract_variables`, `extract_depth_range`, `extract_intent`), causing the UI to freeze for **up to 105 seconds (1.75 minutes)** before falling back. | **High** (whenever Ollama is offline) | Add an upfront ping / availability check or set a fast connect timeout (1.0–2.0 s) on `ollama.Client`. | Small |
| **F-05** | **Safety / UI** | [`app/ui.py:271-278`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L271-L278) | In `_render_pipeline_result`, `clarification.message` is interpolated directly into an HTML block rendered with `unsafe_allow_html=True`. | If a clarification message echoes unescaped user-supplied text containing HTML tags or script injection, it renders directly in the user's browser. | **Medium** | Sanitize using `html.escape()` or render using standard Streamlit markdown `st.warning(...)`. | Small |
| **F-06** | **Edge Case / Error** | [`src/siqva/plots.py:408`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/plots.py#L408) | `_filter_profile` calls `sub["depth_m"] = -gsw.z_from_p(p_arr, lat_val)` without verifying `gsw is not None`. | If `gsw` failed to import, this raises `AttributeError: 'NoneType' object has no attribute 'z_from_p'`. While `pipeline.py` catches `Exception`, the plot disappears with no feedback explaining why. | **Medium** | Guard with `if gsw is not None:` and fallback to pressure or display a clear placeholder annotation. | Small |
| **F-07** | **Scientific Physics** | [`src/siqva/physics.py:219-220`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/physics.py#L219-L220) | `if z_m[0] > 15.0: continue` drops any profile whose shallowest recorded measurement is deeper than 15 metres. | If an Argo float's shallowest sensor point is at 16 dbar (common for floats with surface drift or sensor delays), the entire profile is skipped. If all profiles in a query are affected, the physics table is blank without explanation. | **Medium** | Record dropped profiles and add an explanatory note in `missing_data_notes` explaining why physics could not be computed. | Small |
| **F-08** | **Performance / UI** | [`app/ui.py:248`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py#L248) | `recent_cards = list_cards(limit=10)` executes synchronously at the top level of the Streamlit script on every rerun. | Every user interaction (tab click, slider adjustment, radio button) causes a synchronous SQLite query and JSON deserialization of 10 cards. | **Medium** | Wrap `list_cards` in `@st.cache_data(ttl=5)`. | Small |
| **F-09** | **Docs Drift** | [`docs/CODE_FLOW.md:569`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/docs/CODE_FLOW.md#L569) | `CODE_FLOW.md` claims: *"If the local float-index Parquet file is missing and must be fetched live over ERDDAP, remote index queries take 30-50 seconds..."* | In the actual code (`fetcher.py:141-146`, `718-721`), if `data/float_index.parquet` is missing, the code **never** makes a live ERDDAP index query. It immediately falls back to the cost cap with `profile_count_verified = False`. The documentation is misleading. | **Medium** (documentation inaccuracy) | Update `CODE_FLOW.md` to accurately state that missing float-index files skip pre-fetch guards without making network calls. | Small |
| **F-10** | **Architecture Drift** | [`AGENTS.md:Section 5`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/AGENTS.md#L50-L70), `requirements.txt` | `AGENTS.md` specifies `src/siqva/api.py # FastAPI`, and `requirements.txt` specifies `fastapi` and `uvicorn`. | `src/siqva/api.py` does not exist in the codebase. `fastapi` and `uvicorn` are unused dependencies. | **Medium** | Either implement `src/siqva/api.py` wrapping `pipeline.run()`, or remove `fastapi` and `uvicorn` from `requirements.txt` if headless API is postponed. | Medium |
| **F-11** | **Dead Code** | [`src/siqva/fetcher.py:430-435`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L430-L435) | `create_float_index_snapshot` contains duplicate code after a `return` statement: lines 431–434 repeat the sidecar file write and return. | Unreachable dead code causes maintenance confusion. | **Low** | Remove lines 431–434. | Small |
| **F-12** | **Dead Code** | [`src/siqva/fetcher.py:437-463`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L437-L463) | Function `count_matching_profiles_via_index()` queries the ERDDAP index live, but is never invoked anywhere in the codebase. | Unused function left in the module. | **Low** | Either add an integration test or delete the unused helper. | Small |
| **F-13** | **Deprecation** | [`src/siqva/fetcher.py:876, 894`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/src/siqva/fetcher.py#L876) | Uses `datetime.utcnow().isoformat() + "Z"`. `utcnow()` is deprecated in Python 3.12+ in favor of timezone-aware UTC datetimes. | Future deprecation warning on Python 3.12+. | **Low** | Replace with `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`. | Small |
| **F-14** | **Testing Gap** | [`app/ui.py`](file:///c:/Users/Sagar%20Gowda%20H/OneDrive/Desktop/SIQVA/app/ui.py) | The Streamlit UI has zero automated test coverage. | UI regressions (such as the recent `summary_markdown` attribute crash) cannot be caught by `pytest`. | **Low** | Add a smoke test using `streamlit.testing.v1.AppTest`. | Medium |

---

## 3. Performance Benchmark & Stage Timings

All stages were measured on Windows using Python 3.11 with the standard cached fixture `tests/fixtures/sample_argo_standard.parquet` (188 rows, 2 profiles) across repeated iterations:

### Measured Pipeline Timings

| Pipeline Stage | Function / Module | Execution Time (ms) | Execution Time (s) | Notes |
|---|---|---|---|---|
| **1. Rules Parsing** | `rules_parser.parse_rules` | **0.800 ms** | 0.00080 s | Pure regex & dictionary lookup. Extremely fast. |
| **2. Hybrid Parsing (Rules Path)** | `parser.parse_detailed` | **0.719 ms** | 0.00072 s | Rules resolve completely; zero LLM latency. |
| **3. Spec Validation** | `validator.validate_spec` | **0.001 ms** | 0.00000 s | Bounds & cost cap calculation. Instantaneous. |
| **4. Parquet Cache Load** | `pd.read_parquet` | **1.637 ms** | 0.00164 s | Fast zero-copy PyArrow deserialization. |
| **5. QC Audit** | `qc.audit_qc` | **1.719 ms** | 0.00172 s | Tallies flag distributions without row loss. |
| **6. TEOS-10 Physics** | `physics.compute_new_features` | **3.526 ms** | 0.00353 s | C-extension `gsw` vector routines (MLD, ILD, TCHP, sound speed). |
| **7. Oceanographic Analysis** | `analyzer.analyze` | **8.137 ms** | 0.00814 s | End-to-end statistics, depth bins, and physics aggregation. |
| **8a. Plot: Position Map** | `plots.plot_position_map` | **39.031 ms** | 0.03903 s | Plotly Scattergeo coordinate projection. |
| **8b. Plot: Depth Profile** | `plots.plot_depth_profile` | **14.801 ms** | 0.01480 s | Scatter line plot with reversed pressure axis. |
| **8c. Plot: T-S Diagram** | `plots.plot_ts_diagram` | **13.335 ms** | 0.01334 s | Scatter marker plot with Viridis colormap. |
| **8d. Plot: Thermocline / BLT** | `plots.plot_thermocline_and_barrier` | **23.176 ms** | 0.02318 s | Temperature profile + shaded Barrier Layer polygon. |
| **8e. Plot: Cyclone TCHP** | `plots.plot_cyclone_tchp` | **20.924 ms** | 0.02092 s | 26°C isotherm + shaded thermal energy polygon. |
| **8f. Plot: Acoustic Profile** | `plots.plot_acoustic_profile` | **15.470 ms** | 0.01547 s | Sound speed profile + SLD peak & SOFAR axis lines. |
| **9. Card Build** | `card.build_card` | **0.039 ms** | 0.00004 s | Pydantic model assembly & serialization. |
| **10. SQLite Save** | `card.save_card` | **6.233 ms** | 0.00623 s | SQLite connection, table check, index update, commit. |
| **Total Pipeline (Cached)** | `pipeline.run` | **~148.6 ms** | **~0.149 s** | Very fast end-to-end execution when data is cached. |

### Module Import Overhead (`python -X importtime`)
Cold start import of `siqva` takes **3.090 seconds**. The individual package contributions are:
- `argopy`: **1.950 s** (63% of total import time, due to remote accessor setup and xarray/scipy integrations)
- `pandas`: **0.838 s** (27% of total import time)
- `xarray`: **0.199 s**
- `dateparser`: **0.159 s**
- `ollama`: **0.104 s**
- `pydantic`: **0.063 s**
- `rapidfuzz`: **0.041 s**
- `plotly`: **0.004 s**
- `gsw`: **0.001 s**

### Top 3 Speed-Up Opportunities

1. **Add an Upfront Ollama Connect Timeout / Availability Check (Saves up to 105 seconds)**
   - *Current issue*: When Ollama is stopped, each failed fallback call waits 21 seconds on TCP connect timeout. Five sequential calls take 105 seconds.
   - *Fix*: Check Ollama health once upfront with a 1.0-second timeout. If unreachable, disable LLM fallback immediately.
   - *Estimated Gain*: **105 seconds saved** on ambiguous queries when Ollama is offline.

2. **Streamlit `@st.cache_data` for UI Components (Saves ~135 ms per user click)**
   - *Current issue*: Streamlit reruns the entire script on every user interaction, repeatedly calling `list_cards` (6.2 ms) and regenerating 6 Plotly figures (~126.7 ms).
   - *Fix*: Cache `list_cards` and figure generation functions using `@st.cache_data`.
   - *Estimated Gain*: **~135 ms reduction** in Streamlit rerun latency on every button click or tab switch.

3. **Lazy Import `argopy` in Non-Fetch Operations (Saves ~1.95 seconds on startup)**
   - *Current issue*: Importing `siqva` loads `argopy` at module level, adding ~1.95 seconds to UI startup and CLI tool execution.
   - *Fix*: Defer `import argopy` inside `fetch()` in `fetcher.py`.
   - *Estimated Gain*: **~1.95 seconds faster startup time** for Streamlit and CLI commands that do not immediately fetch remote data.

---

## 4. Analysis of `physics.py`

`src/siqva/physics.py` was introduced to calculate thermodynamic and acoustic ocean parameters using the Gibbs SeaWater TEOS-10 standard (`gsw`):

1. **What it computes**:
   - **Depth in metres**: Derived via `depth_m = -gsw.z_from_p(pres, lat)`. Correctly accounts for latitude-dependent gravitational acceleration.
   - **Absolute Salinity ($S_A$) & Conservative Temperature ($\Theta$)**: Converted from Practical Salinity ($S_P$) and in-situ temperature ($T$) via `gsw.SA_from_SP` and `gsw.CT_from_t`.
   - **Mixed Layer Depth (MLD)**: Density threshold criterion $\Delta \sigma_0 = +0.03\text{ kg/m}^3$ from 10 m reference depth (de Boyer Montégut et al., 2004). Formula is oceanographically standard and correct.
   - **Isothermal Layer Depth (ILD)**: Temperature threshold criterion $\Delta T = -0.2^\circ\text{C}$ from 10 m reference depth. Standard and correct.
   - **Barrier Layer Thickness (BLT)**: $\max(0, \text{ILD} - \text{MLD})$. Standard and correct.
   - **Z20 Isotherm**: Depth where temperature drops below 20°C (thermocline proxy).
   - **Z26 & Tropical Cyclone Heat Potential (TCHP)**: $\int_0^{Z26} \rho \cdot c_{p0} \cdot (T - 26)\, dz$. The formula and unit conversion ($10^7\text{ J/m}^2 = 1\text{ kJ/cm}^2$) are mathematically and physically exact.
   - **Acoustic Waveguide Properties**: Sonic Layer Depth (SLD) and SOFAR Channel Axis minimum sound speed via `gsw.sound_speed`.
2. **Handling of Short / Sparse Profiles**:
   - Profiles with fewer than 5 points (`len(grp) < 5`) are skipped.
   - Profiles starting deeper than 15 m (`z_m[0] > 15.0`) are skipped.
   - The SOFAR channel axis is properly set to `None` if the profile depth is less than 1000 m.
3. **Test Coverage**:
   - `tests/test_physics.py` thoroughly tests synthetic Bay of Bengal temperature inversions, barrier layers, TCHP integrals, and SOFAR depth thresholds (all pass).
4. **Scope Alignment with AGENTS.md**:
   - AGENTS.md explicitly permits standard plots and analyzers, but cautions against feature creep and forecasting. `physics.py` computes diagnostic physical properties with explicit scientific disclaimers (e.g. explicitly stating TCHP does not predict cyclone genesis). However, `physics.py` expanded the spec schema (`spec.py`) with 3 new intents (`thermocline`, `tchp`, `acoustic`) not documented in AGENTS.md Section 7.

---

## 5. Test Coverage Gaps

1. **`app/ui.py` (0% Coverage)**: No automated tests exist for the Streamlit application. Changes to UI state, session keys, or chart rendering are untested by `pytest`.
2. **`src/siqva/api.py` (Missing)**: AGENTS.md Section 5 mentions a FastAPI module, but it does not exist.
3. **Antimeridian Crossing**: No unit tests in `tests/test_validator.py` test longitude ranges crossing 180° (e.g., `lon_min=170, lon_max=-170`).
4. **Non-Indian Ocean Waters in `physics.py`**: Current tests only cover Bay of Bengal / Indian Ocean water masses. There are no tests verifying how `physics.py` behaves on Atlantic or Pacific profiles.
5. **SQLite Locking Under Windows**: `tests/test_card.py` does not test multiple consecutive writes or locked database states.

---

## 6. What Was Not Checked

In accordance with the read-only audit instructions:
1. **Large Live ERDDAP Fetches**: No remote ERDDAP data downloads were executed during this audit to avoid hammering remote IFREMER/Argo servers. All timing and functional checks used existing fixtures and test cases.
2. **Live Ollama Inference**: The local Ollama server was offline during this session (as verified by the 21.0-second socket timeout check), so live LLM token generation speed and VRAM consumption could not be measured directly.
3. **Browser E2E Testing**: Streamlit UI components were analyzed via static inspection and headless execution; no automated browser driver (Cypress/Playwright) was run.

---

## 7. Recommended Fix Order (First 10 Fixes)

The first 10 fixes are grouped into small, cohesive tasks:

### Group 1: Persistence & Crash Prevention (Immediate)
1. **Fix F-01 (SQLite Connection Leak)**: In `src/siqva/card.py`, wrap all SQLite connections in `try ... finally: conn.close()` to prevent file locks on Windows.
2. **Fix F-01b (Pipeline SQLite Guard)**: In `src/siqva/pipeline.py:155`, wrap `save_card()` in a `try/except` block so database write issues do not crash the user query.
3. **Fix F-05 (Sanitize UI HTML)**: In `app/ui.py:271`, replace raw HTML interpolation with standard `st.warning(clarification.message)` or escape HTML with `html.escape()`.

### Group 2: Scientific Accuracy & Geographic Bounds
4. **Fix F-02 (Antimeridian Query Support)**: Update `validator.py` to allow and properly handle bounding boxes crossing 180° longitude.
5. **Fix F-03 (Basin-Aware Water Mass Classification)**: In `physics.py:260-270`, check bounding box coordinates before applying Indian Ocean water-mass heuristics; default to "Unclassified / Outside Indian Ocean Domain" for Atlantic/Pacific queries.
6. **Fix F-07 (Report Skipped Sparse Profiles)**: In `physics.py:219`, log or report profiles skipped due to shallow depth gaps (>15 m) so users understand why physics metrics are absent.

### Group 3: Performance & Reliability
7. **Fix F-04 (Ollama Fast Timeout / Ping)**: In `llm_parser.py`, add a 1.5-second connection check before executing sequential LLM fallbacks.
8. **Fix F-08 (Streamlit Caching)**: Add `@st.cache_data(ttl=5)` to `list_cards()` in `app/ui.py` to eliminate unnecessary disk I/O on every UI interaction.

### Group 4: Codebase & Documentation Cleanup
9. **Fix F-11 & F-12 (Remove Dead Code)**: Remove unreachable lines 431–434 in `fetcher.py` and remove or wire `count_matching_profiles_via_index`.
10. **Fix F-09 & F-10 (Align Documentation & Dependencies)**: Update `docs/CODE_FLOW.md` line 569 to reflect that missing float-index files do not trigger ERDDAP network calls; align `requirements.txt` with actual imports.

