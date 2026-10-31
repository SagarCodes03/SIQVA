# SIQVA Code Flow & System Architecture
*(Smart Interface of Query and Visualization of Argo data — formerly ArgoCard / FloatChat-R)*

This document describes the complete architecture, execution flow, data access rules, and component interactions of **SIQVA**, derived directly from the codebase in `src/siqva/`, `app/`, and `tests/`.

---

## 1. Overview

SIQVA turns a natural-language oceanographic question into a strictly validated, QC-explicit query specification (`QuerySpec`), fetches real Argo ocean float observations through established data access tools (`argopy`), performs deterministic oceanographic and TEOS-10 physical analyses (`gsw`), renders interactive dark-themed Plotly charts, and packages reproducible **Query Cards** and standalone executable Python fetch scripts.

The local Large Language Model (Llama 3.2 3B via Ollama) serves strictly as a bounded translator from natural language into structured query parameters. The LLM is invoked only for fields that deterministic rule-based parsers cannot resolve. Everything after specification generation—data retrieval, quality control filtering, statistical aggregation, physical equations, plot generation, and text formatting—is 100% deterministic code.

### End-to-End System Flow

```text
User Question (Natural Language)
             │
             ▼
   ┌───────────────────┐
   │  rules_parser.py  │ ──► [Dates, Variables, Region, Mode, Intent, Depth]
   └───────────────────┘
             │ (if any required fields missing/ambiguous)
             ▼
   ┌───────────────────┐
   │   llm_parser.py   │ ──► [JSON-Schema Constrained Fallback (Ollama Temp=0)]
   └───────────────────┘
             │
             ▼
   ┌───────────────────┐
   │   validator.py    │ ──► [Physical bounds, dates, variables, cost cap]
   └───────────────────┘
             │
             ├─────────────────────────────────────────┐
             │ (Oversized / Invalid / Missing Year)     │ (Valid Spec)
             ▼                                         ▼
   ┌───────────────────┐                     ┌───────────────────┐
   │ClarificationNeeded│                     │    fetcher.py     │
   └───────────────────┘                     └───────────────────┘
                                                       │
                                   ┌───────────────────┴───────────────────┐
                                   ▼                                       ▼
                         ┌───────────────────┐                   ┌───────────────────┐
                         │  Local Parquet    │                   │   Remote ERDDAP   │
                         │    Data Cache     │                   │ (argopy.DataFetch)│
                         └───────────────────┘                   └───────────────────┘
                                   │                                       │
                                   └───────────────────┬───────────────────┘
                                                       │
                                                       ▼
                                             ┌───────────────────┐
                                             │       qc.py       │ ──► Audit flags (never drop rows)
                                             └───────────────────┘
                                                       │
                                                       ▼
                                             ┌───────────────────┐
                                             │    analyzer.py    │
                                             │   & physics.py    │ ──► Stats, Depth Bins, TEOS-10
                                             └───────────────────┘
                                                       │
                                                       ▼
                                             ┌───────────────────┐
                                             │     plots.py      │ ──► Profiles, Map, T-S, Physics
                                             └───────────────────┘
                                                       │
                                                       ▼
                                             ┌───────────────────┐
                                             │      card.py      │ ──► QueryCard, Script, SQLite
                                             └───────────────────┘
                                                       │
                                                       ▼
                                             ┌───────────────────┐
                                             │     app/ui.py     │ ──► Streamlit Web Interface
                                             └───────────────────┘
```

---

## 2. Module Map

| File | Primary Responsibility |
| :--- | :--- |
| `src/siqva/spec.py` | Defines `QuerySpec`, `BoundingBox`, `DateRange`, `DepthRange`, enums (`Variable`, `DataMode`, `Intent`), canonical serialization, and SHA-256 hashing. |
| `src/siqva/validator.py` | Enforces geographic bounds, chronological date ordering, allowed variables, depth ranges, and depth-scaled query cost caps. |
| `src/siqva/gazetteer.py` | Resolves geographic ocean names to bounding boxes via dictionary lookup, fuzzy matching (`rapidfuzz`), and coordinate regex extraction. |
| `src/siqva/rules_parser.py` | Extracts variables, dates, regions, delivery modes, depth limits, and user intent using deterministic regular expressions and dictionary rules. |
| `src/siqva/llm_parser.py` | Provides JSON-schema-constrained Ollama fallback extraction for individual fields that rule-based parsing leaves unfilled. |
| `src/siqva/parser.py` | Orchestrates the hybrid parsing strategy: runs rules first, calls the LLM fallback only if needed, validates the candidate spec, and returns a `QuerySpec` or `ClarificationNeeded`. |
| `src/siqva/fetcher.py` | Interfaces with `argopy.DataFetcher` using explicit modes, evaluates local float-index profile guards, manages Parquet caching with sidecar JSON, and handles network timeouts. |
| `src/siqva/qc.py` | Documents mode filtering behaviors (research, standard, expert) and performs non-destructive quality control auditing per variable and profile. |
| `src/siqva/analyzer.py` | Calculates non-depth-weighted observation statistics, vertical depth-bin distributions, depth penetration percentages, on-demand physics orchestration, skipped-profile tracking, and deterministic template summaries. |
| `src/siqva/physics.py` | Implements deterministic TEOS-10 thermodynamic and acoustic physical properties (MLD, ILD, BLT, Z20, Z26, TCHP, sound speed, SLD, SOFAR axis) using `gsw`. Executed strictly on-demand for physics intents; water-mass classification permanently removed; tracks skipped profiles via `SkippedProfileInfo`. |
| `src/siqva/plots.py` | Generates interactive Plotly visualizations (depth profiles, spatial trajectories, T-S diagrams, thermocline/barrier layers, cyclone TCHP, sound speed) under the Deep Ocean dark theme. |
| `src/siqva/card.py` | Constructs immutable `QueryCard` provenance records, persists them to SQLite, generates reproducible Python scripts, and computes data diff summaries upon re-run. |
| `src/siqva/pipeline.py` | Chains parsing, validation, data fetching, QC auditing, analysis, visualization, and card persistence into a single end-to-end entry point. |
| `app/ui.py` | Streamlit web application providing natural-language search, interactive multi-mode graph builders, query card inspection, and script downloads. |

---

## 3. Step-by-Step Flow of One Query

When a query is processed through `siqva.pipeline.run(question)`:

1. **Natural Language Input**
   - **File**: `src/siqva/pipeline.py` -> `run(question)`
   - **Input**: User query string (e.g. `"temperature profiles in Arabian Sea in January 2022"`).
   - **Output**: Delegated to `parser.py`.

2. **Parsing (Rules First, LLM Fallback)**
   - **File**: `src/siqva/parser.py` -> `parse_detailed(question)`
   - **Input**: Question string, optional reference `today` date.
   - **Internal Steps**:
     1. Calls `rules_parser.py` -> `parse_rules(question)`.
     2. Extracts dates via regex/dateparser, variables via synonym map, region via gazetteer lookup, depth range via regex, mode via explicit phrases, and intent via keyword rules.
     3. If any required field (`region`, `date_range`, `variables`) remains missing and `allow_llm=True`, calls `llm_parser.py` targeted fallback functions (`extract_intent_llm`, `extract_variables_llm`, `extract_region_name_llm`, `extract_date_range_llm`, `extract_depth_range_llm`).
     4. Default assignments: depth range defaults to `0–500 dbar` when omitted; mode defaults to `DataMode.RESEARCH`.
   - **Output**: `ParseOutcome` containing candidate `QuerySpec` (or `ClarificationNeeded`).

3. **Validation & Size Capping**
   - **File**: `src/siqva/validator.py` -> `validate_spec(spec)`
   - **Input**: Candidate `QuerySpec`.
   - **Checks**:
     - Longitudes within `[-180, 180]` and `lon_min <= lon_max`.
     - Latitudes within `[-90, 90]` and `lat_min <= lat_max`.
     - Dates chronological: `start <= end`.
     - Variables in allowed set (`TEMP`, `PSAL`, `PRES`).
     - Depth range valid: `0 <= min_depth <= max_depth`.
     - Cost estimate cap: `cost = area_deg2 * days * (depth_span / 500.0) <= 15,000.0`.
   - **Output**: Returns `None` if valid; raises `SpecValidationError` or `OversizedRequestError`.

4. **Data Retrieval & Pre-Fetch Guards**
   - **File**: `src/siqva/fetcher.py` -> `fetch(spec)`
   - **Input**: Validated `QuerySpec`, cache parameters.
   - **Internal Steps**:
     1. Evaluates local float index snapshot (`data/float_index.parquet`). If coverage is `FULL`, enforces the 100-profile maximum guard (`DEFAULT_MAX_PROFILE_COUNT = 100`). If coverage is `PARTIAL` or `NOT_COVERED`, skips profile count ceiling, applies only the cost cap, and marks `profile_count_verified = False`.
     2. Computes `fetch_key = spec.fetch_key()`. Checks local Parquet cache (`cache/<fetch_key>.parquet` and sidecar JSON). If present and valid within expiration window (7 days for standard/expert, 90 days for research), loads cached data immediately (`is_cached = True`).
     3. If cache miss, constructs the 8-element bounding box:
        `[lon_min, lon_max, lat_min, lat_max, dpt_min, dpt_max, start_iso, end_iso]`
        and invokes `argopy.DataFetcher(mode=spec.mode.value, src="erddap")`.
     4. Saves retrieved data to Parquet and generates sidecar JSON containing row count, profile count, data hash, versions, and timestamp.
   - **Output**: `FetchResult` (Status: `SUCCESS`, `EMPTY`, `OVERSIZED`, `TIMEOUT`, or `ERROR`).

5. **Quality Control Audit**
   - **File**: `src/siqva/qc.py` -> `audit_qc(df, variables, mode)`
   - **Input**: Fetched DataFrame, variable list, data mode.
   - **Action**: Inspects QC flag columns (`*_QC`, `POSITION_QC`, `TIME_QC`). Counts good (`QC=1`), probably good (`QC=2`), and non-good (`QC!=1`) flags. Identifies profiles containing non-good measurements. **Never removes or modifies rows.**
   - **Output**: `QCReport`.

6. **Deterministic Oceanographic & Physical Analysis**
   - **File**: `src/siqva/analyzer.py` -> `analyze(df, spec, fetch_res)` and `src/siqva/physics.py` -> `compute_new_features(df)`
   - **Input**: Fetched DataFrame, spec, fetch result.
   - **Calculations**:
     - Min, mean, max for each physical variable.
     - Observation means grouped into discrete vertical layers (`0–100 dbar`, `100–500 dbar`, `500–2000 dbar`).
     - Profile depth penetration (% reaching target depth).
     - **On-Demand TEOS-10 Physics via `gsw`**: Executed *only* when `spec.intent` is one of `thermocline`, `tchp`, or `acoustic`. Standard queries (`profile`, `map`, `ts`, `trend`) bypass physics computation completely.
       - Mixed Layer Depth (MLD), Isothermal Layer Depth (ILD), Barrier Layer Thickness (BLT), 20°C isotherm depth (Z20), Tropical Cyclone Heat Potential (TCHP), sound speed, Sonic Layer Depth (SLD), SOFAR axis.
       - Skipped profiles (fewer than 5 observations or shallowest depth > 15 m) are tracked via `SkippedProfileInfo` and explicitly reported in `missing_data_notes` and summary text. Water-mass classification is permanently removed.
   - **Output**: `AnalysisResult`.

7. **Deterministic Summary Generation**
   - **File**: `src/siqva/analyzer.py` -> `summary_text(analysis)`
   - **Input**: `AnalysisResult`.
   - **Action**: Formats structured Markdown using fixed string templates. Never calls an LLM. Clearly labels non-depth-weighted observation averages and attaches scientific methodology disclaimers.
   - **Output**: Formatted summary text (`summary_markdown`).

8. **Visualization Generation**
   - **File**: `src/siqva/plots.py` (orchestrated by `src/siqva/pipeline.py`)
   - **Functions**: `plot_depth_profile`, `plot_position_map`, `plot_ts_diagram`, `plot_thermocline_and_barrier`, `plot_cyclone_tchp`, `plot_acoustic_profile`.
   - **Input**: DataFrame, representative profile physics metrics.
   - **Behavior**: Standard figures (`profile`, `map`, and `ts` when temperature and salinity are present) are generated for standard queries. Physics plots (`plot_thermocline_and_barrier`, `plot_cyclone_tchp`, `plot_acoustic_profile`) are strictly generated on-demand only when the matching physics intent is requested (`Intent.THERMOCLINE`, `Intent.TCHP`, or `Intent.ACOUSTIC`).
   - **Output**: Dictionary of Plotly Figure objects (`dict[str, go.Figure]`).

9. **Query Card Creation & Persistence**
   - **File**: `src/siqva/card.py` -> `build_card(spec, fetch_res, analysis)` and `save_card(card)`
   - **Input**: Spec, fetch result, analysis result.
   - **Action**: Constructs immutable `QueryCard`, writes record to SQLite database (`data/cards.sqlite`), and generates a standalone, runnable Python script (`generate_script`).
   - **Output**: `QueryCard` and Python script string.

10. **UI Presentation**
    - **File**: `app/ui.py` -> `_render_pipeline_result(res)`
    - **Input**: `PipelineResult`.
    - **Display**: Metric tiles (Rows, Profiles, Source, Mode, Depth), interactive Plotly figures, summary markdown, SQLite Query Card metadata, and a script download button.

---

## 4. Data Fetching

### Service and Library
- **Library**: `argopy` (version 1.4.0+).
- **Service**: ERDDAP (`src="erddap"`, default server: `https://erddap.ifremer.fr/erddap`).
- **Data Access API**: `argopy.DataFetcher` for physical profiles; `argopy.IndexFetcher` for metadata index discovery.

### Region Box Format
`argopy` requires an 8-element list in exact sequence:
```python
box = [
    float(lon_min),       # Minimum longitude [-180, 180]
    float(lon_max),       # Maximum longitude [-180, 180]
    float(lat_min),       # Minimum latitude [-90, 90]
    float(lat_max),       # Maximum latitude [-90, 90]
    float(min_depth),     # Shallowest pressure in dbar (e.g. 0.0)
    float(max_depth),     # Deepest pressure in dbar (e.g. 500.0)
    str(date_start_iso),  # Start date in YYYY-MM-DD
    str(date_end_iso),    # End date in YYYY-MM-DD
]
```
Example: `[50.0, 75.0, 10.0, 25.0, 0.0, 500.0, "2022-01-01", "2022-01-10"]`.

### Explicit Mode Control
The delivery mode is explicitly extracted from `QuerySpec.mode.value` and passed directly to the constructor:
```python
fetcher = argopy.DataFetcher(mode=spec.mode.value, src="erddap", api_timeout=timeout)
```
The library default is **never** relied upon.

### Profile Guard & Local Float-Index Snapshot
To avoid multi-minute queries that trigger remote timeouts:
1. `siqva.fetcher.count_profiles_in_snapshot()` queries a local Parquet snapshot (`data/float_index.parquet`) with metadata columns `(wmo, cycle_number, latitude, longitude, date)`.
2. It compares the query bounding box and date range against the recorded snapshot bounds in `data/float_index.json`.
3. If coverage is **`FULL`**, the profile guard enforces `DEFAULT_MAX_PROFILE_COUNT = 100`. Requests exceeding 100 profiles are rejected as `FetchStatus.OVERSIZED`.
4. If coverage is **`PARTIAL`** or **`NOT_COVERED`**, the count is marked unverified (`profile_count_verified = False`), the count ceiling is skipped, and only the geometric cost cap is enforced.

### Size Capping
Cost formula:
$$\text{Cost} = (\text{lon}_{\max} - \text{lon}_{\min}) \times (\text{lat}_{\max} - \text{lat}_{\min}) \times \text{days} \times \left(\frac{\text{depth\_span}}{500.0}\right)$$
Threshold: `DEFAULT_MAX_REQUEST_SIZE = 15,000.0` cost units.

### Failure Handling
- **`TIMEOUT`**: If the remote server takes longer than `timeout` seconds, returns `FetchStatus.TIMEOUT` with user guidance to shrink region or try again later.
- **`EMPTY`**: If no observations match, returns `FetchStatus.EMPTY`. If the query ended within the last 12 months in research mode, it explicitly advises that delayed-mode data may not be finalized and suggests switching to standard mode (`near real-time`).
- **`OVERSIZED`**: Returns `FetchStatus.OVERSIZED` with explicit reduction advice (area, days, or depth).

---

## 5. Pre-Processing and Quality Control (QC)

### Mode Filtering in `argopy`

Based on `argopy` source code and documentation:

1. **Research Mode (`mode="research"`)**:
   - Strictly delayed-mode data (`DATA_MODE == 'D'`). Real-time and near real-time data are excluded.
   - Merges adjusted parameters into primary fields (`TEMP_ADJUSTED -> TEMP`, `PSAL_ADJUSTED -> PSAL`, `PRES_ADJUSTED -> PRES`).
   - Enforces `QC == 1` ("Good") strictly across position, time, and variables (`TEMP_QC == 1`, `PSAL_QC == 1`, `PRES_QC == 1`).
   - Drops measurements where pressure error $\ge 20\text{ dbar}$ (`PRES_ERROR < 20`).
2. **Standard Mode (`mode="standard"`)**:
   - Retains both real-time (`'R'`), adjusted real-time (`'A'`), and delayed-mode (`'D'`) profiles.
   - Merges adjusted fields when available.
   - Retains measurements with `QC == 1` ("Good") and `QC == 2` ("Probably Good"). Flags `0`, `3`, and `4` are excluded.
3. **Expert Mode (`mode="expert"`)**:
   - Identity operation (`lambda x: x`).
   - No data mode filtering (raw `'R'`, `'A'`, `'D'` all present).
   - No QC filtering (all flags 0–9 retained). Raw and adjusted columns are kept separate.

### Profile Counting
Unique profiles are strictly counted by the composite key `(PLATFORM_NUMBER, CYCLE_NUMBER)`:
```python
profile_count = int(df[["PLATFORM_NUMBER", "CYCLE_NUMBER"]].drop_duplicates().shape[0])
```
Counting `CYCLE_NUMBER` alone is invalid because multiple distinct floats share identical cycle numbers simultaneously.

### QC Auditing
`siqva.qc.audit_qc()` evaluates:
- Distribution of each QC flag value ($0, 1, 2, 3, 4, 5, 8, 9$) per variable.
- Number and percentage of non-good flags (`QC != 1`).
- Count of profiles affected by non-good observations.
- Position QC anomalies (`POSITION_QC != 1`).
- **Crucial Rule**: `audit_qc` is purely diagnostic. It **never drops rows silently**.

---

## 6. Caching Architecture

### Cache Key
The cache key is the SHA-256 hash of the normalized fetch dictionary (excluding user intent):
```python
fetch_key = spec.fetch_key()
# Hash of region, date_range, depth_range, variables, and mode
```
Because `intent` (e.g. `map` vs `profile`) does not alter the underlying observations, changing visualization intent reuses the exact same cached data.

### Storage Layout
Under `cache/` (git-ignored):
- Data file: `<fetch_key>.parquet` (Apache Parquet binary table).
- Sidecar metadata: `<fetch_key>.json`.

### Sidecar JSON Fields
```json
{
  "src": "erddap",
  "source": "erddap",
  "argopy_version": "1.5.0",
  "xarray_version": "2026.9.0",
  "fetch_timestamp": "2026-10-30T13:09:55.493199Z",
  "row_count": 14029,
  "profile_count": 42,
  "data_hash": "9c0b80c0a9e3c15fda41e6e447246e755e442f210cd34d2137ee28681165f880",
  "fetch_key": "73c4665acd11d00781e112d289936386c2bd4241f66081714413258eba9dac12"
}
```

### Expiry Rules
Implemented in `is_cache_entry_valid()`:
- **Standard and Expert**: Expires after **7 days** (`DEFAULT_CACHE_EXPIRY_DAYS = 7`).
- **Research**: Expires after **90 days** (`DEFAULT_RESEARCH_CACHE_EXPIRY_DAYS = 90`) OR if the installed `argopy` version changes.
- **Cache Labeling**: When served from cache, `FetchResult.is_cached = True`, triggering a distinct green `CACHE HIT` indicator in the UI.

---

## 7. The LLM Boundary

### Hard Architectural Rule
**The LLM never sees profile data values, statistics, or fetch results.**
The boundary is enforced in `src/siqva/llm_parser.py`: the only inputs accepted by LLM functions are the user's natural language question string and static few-shot examples. No DataFrame, numerical summary, or array is ever passed into a prompt.

### Single-Field Fallback Design
LLM calls are made with:
- Model: `llama3.2` (3B parameters) via Ollama.
- Temperature: `0.0`.
- Format: Strict JSON Schema enforcement.
- Scope: Exactly one field per call.

### Prompts and Schemas

#### 1. Intent Extraction
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "intent": { "type": "string", "enum": ["profile", "map", "ts", "trend"] }
    },
    "required": ["intent"]
  }
  ```
- **System Prompt**:
  > "You are an assistant for oceanographic Argo queries. Classify the user intent into exactly one of: 'profile' (depth profiles/vertical casts), 'map' (spatial distribution/float trajectories/locations), 'ts' (temperature vs salinity diagrams), or 'trend' (time series or temporal changes). Return JSON."

#### 2. Variables Extraction
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "variables": { "type": "array", "items": { "type": "string", "enum": ["TEMP", "PSAL", "PRES"] } }
    },
    "required": ["variables"]
  }
  ```
- **System Prompt**:
  > "Extract requested ocean physical variables from the user query. Valid Argo variables: 'TEMP' (temperature, warm, heat), 'PSAL' (salinity, salt, practical salinity), 'PRES' (pressure). Only include PRES if user explicitly says 'pressure'. Do not map depth or meters to PRES. Return JSON."

#### 3. Date Range Extraction
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "start": { "type": ["string", "null"] },
      "end": { "type": ["string", "null"] }
    },
    "required": ["start", "end"]
  }
  ```
- **System Prompt**:
  > "Extract explicit calendar date ranges into ISO YYYY-MM-DD. If only a single year is given (e.g. 2021), span from YYYY-01-01 to YYYY-12-31. If relative, vague, or missing a year (e.g. 'March', 'recent', 'last month'), never guess: return null for both start and end. Return JSON."

### Validation of LLM Output
Outputs are validated using Pydantic models. If the output fails validation or returns `null` for unanchored dates, the pipeline does **not** guess; it returns `ClarificationNeeded`.

---

## 8. Oceanographic Analysis & Answer Text

All analytical summaries are generated via deterministic code in `src/siqva/analyzer.py` and `src/siqva/physics.py`:

### Intent Grouping
Queries are partitioned into two architectural intent classes:
1. **Standard Queries** (`Intent.PROFILE`, `Intent.MAP`, `Intent.TS`, `Intent.TREND`):
   - Computes standard observation statistics and depth-bin distributions.
   - Bypasses TEOS-10 physical calculations completely.
   - Renders only requested standard figures (`profile`, `map`, or `ts`).
2. **Physics Queries** (`Intent.THERMOCLINE`, `Intent.TCHP`, `Intent.ACOUSTIC`):
   - Invokes deterministic TEOS-10 physical metrics via `physics.compute_new_features()`.
   - Generates specialized on-demand physics figures.
   - Evaluates profile quality criteria and logs skipped profiles.

### Computed Metrics
1. **Physical Variable Statistics**:
   - Total observation count and missing count.
   - Minimum, maximum, and arithmetic mean.
   - Note: Labeled strictly as `"observation mean (not depth-weighted)"` because Argo floats do not sample uniformly in depth.
2. **Discrete Depth Bins**:
   - `0–100 dbar` (Upper mixed layer)
   - `100–500 dbar` (Thermocline layer)
   - `500–2000 dbar` (Intermediate / deep layer)
   - Bins outside the query depth range are omitted.
3. **Vertical Sampling Coverage**:
   - Percentage of profiles reaching the target maximum depth.
   - Shallowest and deepest pressure recorded.
4. **On-Demand TEOS-10 Ocean Physics (`physics.py` via `gsw`)**:
   - **Density MLD**: Depth where potential density increases by $\Delta \sigma_0 = 0.03\text{ kg/m}^3$ from 10 m reference.
   - **Temperature ILD**: Depth where conservative temperature drops by $\Delta T = 0.2^\circ\text{C}$ from 10 m reference.
   - **Barrier Layer Thickness (BLT)**: $\max(0, \text{ILD} - \text{MLD})$.
   - **Z20 Thermocline Proxy**: Depth of the $20^\circ\text{C}$ isotherm.
   - **Tropical Cyclone Heat Potential (TCHP)**: Contiguous upper-layer heat content above $26^\circ\text{C}$:
     $$Q = c_p \rho \int_0^{Z_{26}} (T(z) - 26)\, dz$$
   - **Acoustic Properties**: Sound speed profile via `gsw.sound_speed()`, Sonic Layer Depth (SLD) near-surface peak, and SOFAR channel minimum axis (evaluated only on profiles $\ge 1000\text{ m}$).
   - **Permanent Removal of Water-Mass Heuristic**: Previously hard-coded Indian Ocean salinity/temperature water-mass classification rules were permanently removed because they mislabeled Atlantic and Pacific profiles.
   - **Named Quality Thresholds**:
     - `MIN_PROFILE_OBSERVATIONS = 5`: Profiles with fewer than 5 vertical data points are skipped for physics.
     - `MAX_SURFACE_OBSERVATION_DEPTH_M = 15.0`: Profiles where the shallowest observation starts deeper than 15 m cannot accurately reference surface layer properties and are skipped.
   - **Skipped Profile Tracking**: Profiles failing the above thresholds are recorded via `SkippedProfileInfo` (capturing profile ID, WMO, cycle, and reason) and explicitly reported in `AnalysisResult.missing_data_notes` and deterministic summary text.

### Deterministic Text Templates
The markdown output is constructed by concatenating deterministic formatted blocks in `summary_text()`. No language model generates summary text or numbers.

---

## 9. Plotting Specifications

All plots are generated via Plotly using the Deep Ocean dark theme:
- Canvas background: Transparent / `#0B1F2A`.
- Grid lines: `#1E4558`.
- Text & ticks: `#E6F1F5`.

Standard plots are rendered for standard intents. Physics plots (`plot_thermocline_and_barrier`, `plot_cyclone_tchp`, `plot_acoustic_profile`) are strictly generated on-demand only when their corresponding physics intent (`thermocline`, `tchp`, `acoustic`) is requested.

### Visualizations

| Plot | Data Columns | Visual Elements & Caps |
| :--- | :--- | :--- |
| **Depth Profile** (`plot_depth_profile`) | `PRES`, `TEMP`/`PSAL` | Inverted vertical pressure axis. One colored trace per profile `(PLATFORM_NUMBER, CYCLE_NUMBER)`. Hard-capped at **25 profiles** with an on-screen warning when capped. |
| **Position Map** (`plot_position_map`) | `LONGITUDE`, `LATITUDE`, `PLATFORM_NUMBER`, `TIME` | Scatter plot showing float trajectory lines connected chronologically, with start and end points highlighted. |
| **T-S Diagram** (`plot_ts_diagram`) | `PSAL`, `TEMP`, `PRES` | Practical Salinity on x-axis vs Conservative/In-situ Temperature on y-axis, with overlaid isopycnal contours ($\sigma_0$) calculated via `gsw.sigma0`. |
| **Thermocline & Barrier Layer** (`plot_thermocline_and_barrier`) | `PRES`, `TEMP`, `PSAL` | Dual-panel vertical profile displaying MLD (density), ILD (temperature), and shaded Barrier Layer region. |
| **Cyclone TCHP** (`plot_cyclone_tchp`) | `PRES`, `TEMP` | Vertical temperature profile with dashed $26^\circ\text{C}$ threshold and amber shaded integration region down to $Z_{26}$. |
| **Acoustic Profile** (`plot_acoustic_profile`) | `PRES`, `TEMP`, `PSAL` | Vertical sound speed profile (1450–1550 m/s) with Sonic Layer Depth peak and SOFAR minimum channel axis. |

---

## 10. Query Card and Re-Run Diffing

### Immutable `QueryCard`
Stored in SQLite database (`data/cards.sqlite`, table `query_cards`):
- `card_id`: 16-hex-character unique identifier.
- `spec`: Full `QuerySpec` model and normalized JSON.
- `spec_hash`: SHA-256 hash of the complete query specification.
- `fetch_key`: SHA-256 hash of data fetch parameters.
- `mode`: Data delivery mode (`research`, `standard`, `expert`).
- `qc_filter_description`: Human-readable QC policy summary.
- `effective_depth_range`: Min and max depth applied.
- `source`: Access protocol (`erddap`).
- `argopy_version`, `xarray_version`: Exact library versions used.
- `fetch_timestamp`: ISO 8601 UTC timestamp.
- `data_hash`: Canonical SHA-256 hash of fetched observation table.
- `row_count`, `profile_count`: Verified counts.

### Canonical Data Hash
`compute_canonical_data_hash(df)` guarantees deterministic hashing across environments:
1. Retains core variables: `PLATFORM_NUMBER`, `CYCLE_NUMBER`, `PRES`, `TEMP`, `PSAL`, `LATITUDE`, `LONGITUDE`.
2. Rounds floating point values to 4 decimal places.
3. Sorts rows deterministically by `(PLATFORM_NUMBER, CYCLE_NUMBER, PRES)`.
4. Computes SHA-256 over UTF-8 CSV representation.

### Standalone Python Script
`generate_script(card)` creates an executable, reproducible Python script containing the exact `argopy.DataFetcher` parameters, bounding box, and profile-counting logic.

### Re-Run & Data Diffing
`rerun(card)`:
- Re-fetches the dataset using the card's original parameters (bypassing cache).
- Recomputes the canonical data hash.
- Generates a `DiffSummary` detailing:
  - Identical status (`True`/`False`).
  - Added or missing profile IDs.
  - Row count changes (e.g. from newly available delayed-mode adjustments).
  - Explicit notification that data drift in Argo is expected as floats are re-calibrated.

---

## 11. Error Handling and Logging

### Pipeline Statuses
The pipeline reports six explicit status codes via `PipelineStatus`:
1. `SUCCESS`: Valid query, observations fetched, analysis and card completed.
2. `CLARIFICATION_NEEDED`: Ambiguous or missing parameters requiring user input.
3. `EMPTY`: Valid query, but zero observations found within region/time window.
4. `OVERSIZED`: Query exceeds geometric cost threshold ($15,000$) or profile count limit ($100$).
5. `TIMEOUT`: Remote data server failed to respond within timeout window.
6. `ERROR`: Network failure, malformed parameters, or unhandled exceptions.

### Safe Error Messages
Under unexpected exceptions, `PipelineResult` catches errors, generates a safe user-facing message with an 8-character reference ID, and writes full stack traces to `logs/siqva.log` via Python's rotating logger.

---

## 12. Two Worked Examples Traced End to End

### Example 1: Successful Query
**User Question**:
`"temperature and salinity profiles in Arabian Sea between 2022-01-01 and 2022-01-10"`

1. **Rules Extraction**:
   - `variables`: `[Variable.TEMP, Variable.PSAL]` (matched synonyms "temperature", "salinity").
   - `region`: Arabian Sea matched in gazetteer -> `lon: [50.0, 75.0], lat: [10.0, 25.0]`.
   - `date_range`: `start = 2022-01-01`, `end = 2022-01-10`.
   - `depth_range`: `None` -> defaults to `0.0–500.0 dbar`.
   - `mode`: Not specified -> defaults to `DataMode.RESEARCH`.
   - `intent`: Matched keyword "profiles" -> `Intent.PROFILE`.
   - `missing`: `[]`, `ambiguous`: `[]`.
   - **LLM Call**: Not invoked (`allow_llm=False` or skipped).

2. **Generated `QuerySpec` JSON**:
   ```json
   {
     "date_range": {
       "end": "2022-01-10",
       "start": "2022-01-01"
     },
     "depth_range": {
       "max_depth": 500.0,
       "min_depth": 0.0
     },
     "intent": "profile",
     "mode": "research",
     "region": {
       "lat_max": 25.0,
       "lat_min": 10.0,
       "lon_max": 75.0,
       "lon_min": 50.0
     },
     "variables": [
       "PSAL",
       "TEMP"
     ]
   }
   ```
   - Spec Hash: `be23155d02d8765eb6687c0c4606f23f530455dcbb69e096f3075c13bfd4d3e3`
   - Fetch Key: `73c4665acd11d00781e112d289936386c2bd4241f66081714413258eba9dac12`

3. **Validation**:
   - Area: $25^\circ \times 15^\circ = 375^\circ{}^2$.
   - Days: 10.
   - Depth factor: $500 / 500 = 1.0$.
   - Request Cost: $375 \times 10 \times 1.0 = 3,750\text{ cost units} < 15,000$. **Passed.**

4. **Fetch & QC**:
   - Remote fetch via `argopy.DataFetcher(mode="research", src="erddap")`.
   - Returned: 14,029 rows across 42 profiles.
   - QC Audit: 100% `QC=1` (good data), 0 non-good rows.

5. **Outcome**: `PipelineStatus.SUCCESS`, interactive figures generated, QueryCard saved to SQLite.

---

### Example 2: Ambiguous Query (Clarification Required)
**User Question**:
`"salinity profiles in North Atlantic in March"`

1. **Rules Extraction**:
   - `variables`: `[Variable.PSAL]` (matched "salinity").
   - `region`: North Atlantic matched in gazetteer -> `lon: [-80.0, 0.0], lat: [0.0, 65.0]`.
   - `date_range`: `None`. "March" detected without a year.
   - `ambiguous`: `["date_range"]`.
   - Note generated: `"Month 'March' specified without a calendar year. Argo data spans multiple decades; guessing a year is prohibited."`

2. **Candidate Spec Generation**: Blocked. Never guesses a year.

3. **Output Clarification Object**:
   ```json
   {
     "message": "Month 'March' specified without a calendar year. Please provide an explicit 4-digit year (e.g. 'March 2022').",
     "missing_fields": [],
     "ambiguous_fields": [
       "date_range"
     ],
     "suggestions": [
       "Please specify a 4-digit calendar year (e.g. 'March 2022' or 'between 2022-03-01 and 2022-03-31')."
     ]
   }
   ```
4. **Outcome**: `PipelineStatus.CLARIFICATION_NEEDED`. No network call made. Clean warning banner displayed in UI.

---

## 13. Known Limitations and Discrepancy Audit

### Known Limitations
1. **Missing Local Float Index**: If the local float-index Parquet file (`data/float_index.parquet`) is missing or does not cover the query window, the system makes NO live network call to ERDDAP. Instead, it falls back to the geometric cost cap and marks `profile_count_verified = False`.
2. **Provisional Size & Profile Caps**: The 15,000 cost unit limit and 100-profile maximum are provisional thresholds calibrated against regional Indian Ocean and North Atlantic queries.
3. **Deep Sound Speed Accuracy**: Profiles shallower than 1000 m cannot calculate the SOFAR channel axis minimum, as the deep sound channel minimum typically resides between 800 and 1200 m depth.
4. **No BGC or Deep Argo**: Core physical variables (`TEMP`, `PSAL`, `PRES`) down to 2000 dbar are supported. Biogeochemical (oxygen, pH, chlorophyll) and Deep Argo (>2000 dbar) sensors are post-MVP scope.
5. **Antimeridian Crossings**: Bounding boxes crossing the 180° meridian (where `lon_min > lon_max`) are rejected by the validator as out of bounds.

### Discrepancy Audit with AGENTS.md

| Topic | AGENTS.md Statement | Implementation Status / Code Reality |
| :--- | :--- | :--- |
| **Project Name** | Formerly referenced `ArgoCard` and `FloatChat-R`. | Completely renamed to **SIQVA** (package `siqva`, app `SIQVA`). |
| **Physics Features** | Section 3 notes scope control for post-MVP; Section 7 documents on-demand physics intents (`thermocline`, `tchp`, `acoustic`). | Deterministic TEOS-10 thermodynamics and acoustics (MLD, ILD, BLT, Z20, TCHP, SLD, SOFAR) are computed on-demand strictly when requested by their specific physics intent, using `gsw` with zero LLM involvement. |
| **Water-Mass Classification** | Permanent removal noted in Section 7. | Hard-coded Indian Ocean water-mass heuristics were permanently removed to eliminate inaccurate classification in other basins. |
| **Cost Cap Scaling** | Section 7 specifies bounding box and date range validation. | The cost cap was enhanced to include vertical depth scaling: $\text{Area} \times \text{Days} \times (\text{Depth} / 500\text{ dbar})$. |
| **Float Index Cache** | Section 11 permits local Parquet snapshot for discovery. | Implemented via `data/float_index.parquet` and sidecar `data/float_index.json`, used strictly for profile count guards. Missing index makes no network calls. |

