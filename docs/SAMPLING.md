# SIQVA Deterministic Profile Sampling & Float Index Architecture

This document specifies the design, constants, algorithms, capability matrix, and maintenance workflows for the local float index and deterministic profile sampling system in **SIQVA**.

---

## 1. Motivation & Core Philosophy

Oceanographic inquiries often span entire ocean basins (e.g. *"temperature in the Indian Ocean in 2023"*) or multi-year epochs containing tens of thousands to millions of Argo profiles. Attempting to fetch and assemble millions of observations synchronously over remote ERDDAP APIs causes network timeouts, browser stalls, server overload, and bad user experience.

SIQVA solves this through **Deterministic Space-Time Profile Sampling** guided by an in-memory **Local Float Index**:
1. **The LLM Never Sees Data**: Query specifications (`QuerySpec`) are derived deterministically or via schema-constrained translation. The LLM never touches index rows, profile coordinates, or observation values.
2. **Determinism & Reproducibility**: Given the same question and index build date, the sampler always selects the exact same profiles via deterministic hashing (`sha256(fetch_key + build_date)`). Standalone reproduction scripts fetch exactly those profiles without needing the float index.
3. **Scientific Honesty (No Regional Statistics on Samples)**: A sample of 12 or 24 profiles is an illustrative slice, not a regional climatology. SIQVA strictly suppresses regional averages, area statistics, and physics summaries on sample runs.
4. **No Dead Ends**: When a query cannot be fulfilled in full (e.g. basin-wide trend or statistical operation), SIQVA never returns an empty rejection; it provides structured, interactive alternative options.

> [!IMPORTANT]
> **Heuristic Defaults Disclaimer**: All thresholds, cost limits, and profile counts described below are heuristic defaults established during MVP development. They are subject to empirical calibration against real-world network latency and server capacity.

---

## 2. Capacity Constants & Heuristic Limits

The execution planner (`planner.py`) and chunking engine (`chunking.py`) enforce the following constants:

| Constant | Default Value | Description |
| :--- | :--- | :--- |
| `MAX_FULL_ROWS` | `15,000` cost units | Single-request geometric cost cap: $\text{Area}(\text{deg}^2) \times \text{Days} \times \max(1.0, \Delta\text{Depth}/500\text{ dbar})$. |
| `MAX_PROFILE_COUNT` | `100` profiles | Maximum profile ceiling for a single continuous bounding box fetch when full index coverage is available. |
| `SIQVA_MAX_CHUNKS` | `24` months | Maximum calendar-month chunks allowed for multi-month queries under the chunking mechanism. |
| `SIQVA_MAX_TOTAL_ROWS` | `3,000,000` rows | Cumulative row safety cap for concatenated monthly chunks. |
| `LEVELS_PER_DBAR` | `2.0` levels/dbar | Heuristic estimate of vertical measurement resolution per decibar. |
| `DEFAULT_SAMPLE_SIZE`| `12` profiles | Default profile pick count when a query falls back to sampling. |
| `SAMPLE_STEPS` | `(12, 24, 48)` | Step sequence for interactive sample enlargement in the UI. |
| `SAMPLE_MAX` | `50` profiles | Hard ceiling on deterministic profile sample selection. |
| `FOREGROUND_BUDGET` | `90` seconds | Foreground wall-clock timeout protecting the UI against hung remote fetches. |

---

## 3. Capability Profiles Matrix (`capabilities.py`)

Every query intent is categorized under an explicit capability tier:

| Capability Tier | Supported Intents / Subsystems | Allowed Execution Modes | Behavior on Oversized / Basin Query |
| :--- | :--- | :--- | :--- |
| **`METADATA`** | Float overview maps, profile counts, float track inspection | Instant Index Metadata | Queries local float index directly without network calls; renders interactive Scattergeo map and profile counts. |
| **`SAMPLE_ALLOWED`** | Depth profiles (`profile`), T-S diagrams (`ts`), acoustic sound speed (`acoustic`) | `FULL`, `CHUNKED`, `SAMPLE` | Evaluated by planner. If oversized or basin, executes deterministic space-time stratified sampling (`12`, `24`, or `48` profiles). |
| **`FULL_REQUIRED`** | Temperature/Salinity trends (`trend`), thermocline/barrier layers (`thermocline`), cyclone heat potential (`tchp`), numerical operations (`operations.py`), comparisons (`comparison.py`) | `FULL`, `CHUNKED` | Refused (`PlanDecision.REFUSE`) with actionable, non-dead-end options. Samples are never permitted because regional aggregates cannot be computed from sparse samples. |

---

## 4. Float Index Architecture (`floatindex.py`)

### Snapshot Storage & Schema
The float index is stored in Apache Parquet format at `data/float_index.parquet` with an accompanying metadata sidecar `data/float_index.json`.

Schema columns:
- `wmo` (int64): World Meteorological Organization platform identifier (e.g. `2901633`).
- `cycle_number` (int64): Float profile cycle number (e.g. `45`).
- `cycle` (int64): Alias for cycle number.
- `latitude` (float64): Profile surface float latitude in degrees ($[-90, 90]$).
- `longitude` (float64): Profile surface float longitude in degrees ($[-180, 180]$).
- `date` (object / ISO timestamp): Profile observation timestamp (e.g. `2023-05-12T10:14:00Z`).
- `ocean` (string): Canonical ocean basin code: `'I'` (Indian), `'P'` (Pacific), `'A'` (Atlantic).
- `is_delayed` (bool): `True` if delayed-mode quality control has been completed; `False` if real-time.
- `institution` (string): Assembly Center / Data Center code (e.g. `'AO'`, `'IN'`, `'CS'`).

### In-Memory Lifecycle
- **Load Once**: Loaded lazily on first access into an in-memory `FloatIndex` singleton.
- **Zero Network Invocations**: Index lookups, counts, bounding box filtering, and sample selection run entirely in memory using vectorized `pandas` operations.
- **Coverage Status**:
  - `FULL`: Query dates and region fall completely within index temporal and spatial bounds.
  - `PARTIAL`: Date range overlaps the index boundary.
  - `NOT_COVERED`: Query falls entirely outside the index range (e.g. pre-Argo era or future dates).

---

## 5. Rebuilding & Monthly Refresh

### Initial Build
To build or rebuild the float index snapshot from official GDAC / ERDDAP metadata:
```bash
python scripts/build_float_index.py --output data/float_index.parquet
```

The script:
1. Downloads the global Argo index (`ar_index_global_prof.txt.gz`) or queries the ERDDAP float index endpoint.
2. Normalizes column headers, strips whitespace, converts coordinate systems, and maps ocean basin identifiers.
3. Writes the compressed Parquet file to `data/float_index.parquet` and sidecar metadata to `data/float_index.json` (recording `build_date`, `min_date`, `max_date`, and total profile count).

### Monthly Refresh Procedure
Argo floats upload profiles every 10 days, and delayed-mode quality control updates older profiles periodically. To perform a monthly refresh:
1. Run `python scripts/build_float_index.py --update`.
2. Inspect the output summary: total profiles added, delayed-mode flags updated, and new `max_date`.
3. Verify that `pytest tests/test_floatindex.py` passes cleanly.
4. Commit updated `data/float_index.parquet` and `data/float_index.json`.

---

## 6. Deterministic Sample Selection Algorithm (`select_sample`)

When the planner decides `PlanDecision(decision="sample", sample_size=N)`:

1. **Candidate Retrieval**:
   - Resolves region geometry (bounding box or ocean basin code).
   - Filters `df` by spatial bounds and `date_range`.
2. **Deterministic Seed Derivation**:
   ```python
   fetch_key = spec.fetch_key()
   build_date_str = str(index.build_date or "")
   combined = f"{fetch_key}_{build_date_str}".encode("utf-8")
   seed = int(hashlib.sha256(combined).hexdigest()[:8], 16)
   ```
3. **Space-Time Stratification**:
   - Divides the bounding box into a 2D spatial grid (e.g. $3 \times 3$ or $4 \times 4$ latitude/longitude bins).
   - Divides the date range into chronological time slices.
   - Combines bins into space-time strata.
4. **Float Deduplication**:
   - Picks profiles evenly across strata while maximizing distinct `wmo` platform identifiers.
   - If distinct floats are exhausted, allows multiple cycles from the same float.
5. **Output**:
   - Returns `SampleSelection(picks=[SamplePick(...)], method="stratified_space_time", seed=seed, n_available=count, n_requested=N)`.

---

## 7. Sample Fetching & Single-Profile Caching (`fetch_sample`)

1. **Sequential Fetching**:
   - The fetcher iterates through the picked `SamplePick` items.
   - Each pick is retrieved using `argopy.DataFetcher().profile(wmo, cycle)` (or targeted mini-box fallback).
2. **Single-Profile Cache**:
   - Each profile is cached independently in Parquet format:
     `cache/prof_<mode>_<variables>_<wmo>_<cycle>.parquet`.
   - Re-running overlapping sample queries reuses cached profiles instantly.
3. **90-Second Wall-Clock Budget**:
   - If total elapsed fetch time reaches 90 seconds, fetching stops immediately.
   - Successfully fetched profiles are returned; missing profiles are reported cleanly (`"k of n profiles fetched"`).
4. **No Regional Statistics**:
   - `analyzer.py` checks `fetch_result.is_sample`.
   - Regional averages, depth-layer aggregations, and physics summaries are suppressed.
   - Summary text states clearly that the observations represent an illustrative sample.

---

## 8. Standalone Reproducibility & Query Cards

1. **Card Records**:
   - Every `QueryCard` persists `plan_decision="sample"`, `sample_picks=[(wmo, cycle), ...]`, `sample_method`, `sample_seed`, and `sample_index_build_date`.
2. **Standalone Script (`generate_script`)**:
   - Generates executable Python code that fetches the exact picked profiles directly by `(wmo, cycle)`.
   - **No Float Index Required**: Anyone running the generated script gets the exact same profiles without needing `data/float_index.parquet`.
   - **Honest Header**: Explicitly notes that the script reproduces the picked sample rather than the full ocean region.
3. **Re-Run Verification**:
   - Clicking "Re-run" on a sample query card re-fetches the identical `(wmo, cycle)` profiles and compares canonical SHA-256 data hashes to detect upstream delayed-mode updates.

---

## 9. UI & Cross-Feature Integration

- **Dual-Pane Visualization**:
  - Sample runs display the regional **Overview Float Map** (`render_index_overview_map`) showing all float trajectories in the region alongside individual depth profile curves for the sampled floats.
- **Refinement Actions**:
  - Interactive buttons allow users to enlarge the sample (`Bigger sample (24)`), narrow the time window, drill down to named subregions, switch to float-location metadata, or run full data (if within caps).
- **Compare Runs Page**:
  - Compares only complete runs (`FULL` or `CHUNKED`). If a user attempts to compare a sample run, the page refuses with an explanation that sparse samples cannot serve as regional baselines and offers options.
- **Plot Graph Page**:
  - Each plot configuration card displays its capability tier badge (`Metadata`, `Sample allowed`, or `Full data required`) and enforces planner rules before submission.

