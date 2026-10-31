# SIQVA (formerly SIQVA / SIQVA) — TEOS-10 Ocean Physics Architecture & Context

> **Source of Truth & Reference Guide**  
> This file records the complete architecture, implementation details, scientific methodology, test coverage, and validation instructions for the SIQVA (formerly SIQVA / SIQVA) platform following the integration of the TEOS-10 Ocean Physics features.

---

## 1. Project Overview & Hard Scientific Rules

SIQVA turns natural-language oceanographic questions into validated, QC-explicit **query specifications**, fetches real Argo float observations via established tools (`argopy`), computes deterministic thermodynamic and acoustic quantities via TEOS-10 (`gsw`), generates interactive dark-themed Plotly visualizations, and packages reproducible **query cards**.

### Non-Negotiable Hard Rules (from `AGENTS.md`)
1. **The LLM never sees raw data values.** It only converts questions into a constrained query spec.
2. **All numbers and summaries come from deterministic Python code.** Zero LLM-generated numerical summaries or hallucinated statistics.
3. **QC flags and data modes are explicit.** Default is `research` mode (delayed-mode QC=1). `standard` (QC 1-2) and `expert` (raw 0-9) are explicit.
4. **Reproducibility.** Every query generates a card with environment versions (`argopy`, `xarray`), SHA-256 data hash, query parameters, and a standalone runnable Python script.

---

## 2. Integrated TEOS-10 Ocean Physics Engine (`src/siqva/physics.py`)

The physics engine computes standardized oceanographic and acoustic metrics according to internationally recognized oceanographic definitions:

### A. Mixed Layer Depth (MLD) & Barrier Layer Thickness (BLT)
- **Reference Depth**: $10\text{ m}$ reference depth ($Z_{\text{ref}}$) per *de Boyer Montégut et al. (2004)* to avoid diurnal skin-layer heating.
- **Density MLD**: First upward crossing of potential density anomaly $\Delta\sigma_0 = +0.03\text{ kg/m}^3$ relative to $10\text{ m}$.
- **Isothermal Layer Depth (ILD)**: First downward crossing of temperature $\Delta T = -0.2^\circ\text{C}$ relative to $10\text{ m}$.
- **Barrier Layer Thickness (BLT)**: $\max(0, \text{ILD} - \text{MLD})$. When strong freshwater river plumes (e.g. Ganges-Brahmaputra in Bay of Bengal) stratify the near-surface, MLD is much shallower than ILD, creating a salinity-stratified barrier layer that inhibits vertical mixing.

### B. Thermocline Proxy ($Z_{20}$) & Cyclone Heat Potential ($Z_{26}$, TCHP)
- **$Z_{20}$ Isotherm**: First downward crossing of $20.0^\circ\text{C}$ representing the core of the tropical thermocline.
- **$Z_{26}$ Isotherm**: First downward crossing of $26.0^\circ\text{C}$, the thermodynamic lower threshold for tropical cyclone intensification.
- **Tropical Cyclone Heat Potential (TCHP)**: Contiguous upper-layer thermal reservoir integrated from surface down to $Z_{26}$ (*Leipper & Volgenau, 1972*; *Mainelli et al., 2008*):
  $$\text{TCHP} = \int_{0}^{Z_{26}} \rho(z) \cdot c_p \cdot (T(z) - 26.0)\, dz$$
  Computed using TEOS-10 in-situ density $\rho(z)$ and seawater specific heat $c_{p0} = 3991.868\text{ J/(kg}\cdot\text{K)}$. Deep warm inversions below cooler water $< 26^\circ\text{C}$ are strictly excluded. Values $> 60\text{–}80\text{ kJ/cm}^2$ indicate high ocean thermal heat content favorable for rapid cyclone intensification.

### C. TEOS-10 Acoustic Properties (SLD & SOFAR Channel)
- **Sound Speed Profile**: Derived from Absolute Salinity ($S_A$), Conservative Temperature ($\Theta$), and sea pressure via `gsw.sound_speed`.
- **Sonic Layer Depth (SLD)**: Near-surface acoustic duct maximum sound speed located within the upper layer $\le \min(300\text{ m}, Z_{20})$.
- **SOFAR Channel Axis**: Deep sound speed minimum waveguide. Strictly requires profile sampling depth $\ge 1000\text{ m}$; returns `None` for shallow profiles ($< 1000\text{ m}$) as they do not sample the deep acoustic waveguide.

### D. Subsurface Water Mass Classification Heuristic
- Uses isopycnal layer $\sigma_0 \in [23.5, 25.5]\text{ kg/m}^3$:
  - **ASHSW**: Arabian Sea High Salinity Water ($\text{PSAL} \ge 35.8$, $\text{Lat} \ge 5^\circ\text{N}$).
  - **BoBW**: Bay of Bengal Low-Salinity Plume ($\text{PSAL} \le 33.5$, $\text{Lat} \ge 5^\circ\text{N}$).
  - **SIOW**: Southern Indian Ocean Water ($\text{Lat} < -5^\circ$).
  - **Transitional**: Equatorial / Transitional Indian Ocean Water.

---

## 3. End-to-End Pipeline & Module Structure

```
Streamlit UI (app/ui.py)
   │
   ▼
Pipeline (src/siqva/pipeline.py)
   │
   ├── Parser (rules_parser.py -> Intent, BoundingBox, DateRange, Variables, Mode)
   ├── Validator (validator.py -> geographic bounds, date order, cost limit)
   ├── Fetcher (fetcher.py -> argopy / ERDDAP client, Parquet cache)
   ├── QC Filter (qc.py -> mode filter: research=QC 1, standard=QC 1-2, expert=all)
   ├── Physics Engine (physics.py -> TEOS-10 MLD, BLT, Z20, TCHP, SLD, SOFAR)
   ├── Analyzer (analyzer.py -> deterministic statistics, markdown summaries)
   ├── Plot Visualizer (plots.py -> Plotly Deep Ocean dark theme figures)
   └── Card Builder (card.py -> SQLite metadata, reproducibility diff, Python script)
```

### Key Files Modified & Created:
- **`src/siqva/spec.py`**: Added `Intent.THERMOCLINE`, `Intent.TCHP`, `Intent.ACOUSTIC`. Added `ensure_physics_variables` validator ensuring `TEMP`, `PSAL`, and `PRES` are automatically populated.
- **`src/siqva/rules_parser.py`**: Added rule-based extraction for physics intents, handling profile keyword overlap and auto-injecting physical variables.
- **`src/siqva/physics.py`**: Deterministic TEOS-10 physics module (`compute_new_features`, `ProfilePhysicsSummary`, `build_feature_context`, disclaimers).
- **`src/siqva/analyzer.py`**: Extended `AnalysisResult` with `physics_summaries` and `summary_markdown`. Injected dataset-wide physics statistics, per-profile markdown tables, and mandatory scientific methodology notes.
- **`src/siqva/plots.py`**: Added `plot_thermocline_and_barrier`, `plot_cyclone_tchp`, and `plot_acoustic_profile` styled under the Deep Ocean dark theme.
- **`src/siqva/pipeline.py`**: Populates `figures["thermocline"]`, `figures["tchp"]`, and `figures["acoustic"]` whenever physics summaries are computed.
- **`app/ui.py`**: Extended Streamlit UI with new sample queries, visualization charts, and interactive TEOS-10 profile metrics table in the summary tab.
- **`tests/test_physics.py`**: Verification test suite with synthetic physical profiles and live argopy smoke test.

---

## 4. Prompts to Test the New Features

Open your browser at **`http://localhost:8501`** and test the following sample queries:

### Feature 1: Thermocline, MLD & Barrier Layer
**Test Prompt:**
```text
thermocline and barrier layer in Bay of Bengal between 2022-04-01 and 2022-04-15
```
**What to verify in the UI:**
- **Intent**: Resolved automatically to `thermocline`.
- **Variables**: `PRES`, `PSAL`, `TEMP` automatically included.
- **Visualizations Tab (`📊 Visualizations`)**:
  - Shaded purple **Barrier Layer** between Density MLD and Temp ILD.
  - Dashed Teal line for **Density MLD** ($\Delta\sigma_0 = +0.03\text{ kg/m}^3$).
  - Dashed Amber line for **Temp ILD** ($\Delta T = -0.2^\circ\text{C}$).
  - Dotted Emerald line for **$Z_{20}$ Thermocline Proxy**.
- **Summary & Statistics Tab (`📋 Summary & Statistics`)**:
  - Dataset mean/min/max for MLD, ILD, BLT, and $Z_{20}$.
  - Interactive dataframe table listing per-profile physics values.
  - Scientific Methodology & Scope Notes displayed.

---

### Feature 2: Tropical Cyclone Heat Potential (TCHP) & $Z_{26}$
**Test Prompt:**
```text
cyclone heat potential tchp in Arabian Sea in May 2022
```
**What to verify in the UI:**
- **Intent**: Resolved automatically to `tchp`.
- **Visualizations Tab (`📊 Visualizations`)**:
  - Vertical dashed red threshold line at $26.0^\circ\text{C}$.
  - Horizontal dotted orange line at $Z_{26}$ isotherm depth.
  - Warm shaded polygon indicating **TCHP Integrated Area ($\text{kJ/cm}^2$)**.
- **Summary & Statistics Tab (`📋 Summary & Statistics`)**:
  - Dataset mean and maximum TCHP values in $\text{kJ/cm}^2$.
  - Per-profile $Z_{26}$ and TCHP readings.
  - Mandatory Leipper & Volgenau (1972) / Mainelli et al. (2008) scientific guardrail.

---

### Feature 3: TEOS-10 Acoustic Sound Speed Profile, SLD & SOFAR Axis
**Test Prompt:**
```text
acoustic sound speed profile in Arabian Sea between 2022-01-01 and 2022-01-10
```
**What to verify in the UI:**
- **Intent**: Resolved automatically to `acoustic`.
- **Visualizations Tab (`📊 Visualizations`)**:
  - Teal curve of sound speed ($\text{m/s}$) vs depth ($\text{m}$).
  - Cyan diamond marker at **Sonic Layer Depth (SLD Peak)**.
  - Violet star marker at deep **SOFAR Channel Axis** (for deep profiles $\ge 1000\text{ m}$).
- **Summary & Statistics Tab (`📋 Summary & Statistics`)**:
  - Mean SLD and SOFAR channel axis depths.
  - Profiles with depth $< 1000\text{ m}$ correctly display SOFAR Axis as `None`.
  - TEOS-10 acoustic disclaimer and acoustic duct methodology note.

---

## 5. Verification & Test Suite

Run pytest locally from the project root:
```bash
# Run all offline unit tests (166 tests)
.\.venv\Scripts\pytest.exe -m "not network"

# Run the physics test suite
.\.venv\Scripts\pytest.exe tests/test_physics.py -m "not network"
```
**Test Results:**
- 166 passed, 3 skipped, 1 deselected in ~6 seconds.
- Zero regressions against pre-existing test suites (`test_analyzer.py`, `test_card.py`, `test_fetcher.py`, `test_gazetteer.py`, `test_parser.py`, `test_pipeline.py`, `test_plots.py`, `test_qc.py`, `test_rules_parser.py`, `test_spec.py`, `test_validator.py`).

---

## 6. How to Run Locally

```powershell
# Set PYTHONPATH to include src and launch Streamlit on port 8501
$env:PYTHONPATH="src"
.\.venv\Scripts\streamlit.exe run app/ui.py --server.port 8501
```
The app runs at **`http://localhost:8501`**.
