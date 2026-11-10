# SIQVA: Smart Interface for Query and Visualization of Argo Data

**SIQVA** translates natural-language oceanographic questions into validated, quality-control-explicit query specifications, fetches live observations through `argopy`, performs deterministic TEOS-10 thermodynamics and acoustics calculations (`gsw`), renders interactive Plotly visualizations, and generates reproducible **Query Cards** containing cryptographic data hashes and standalone runnable Python scripts.

---

## 1. Core Principles & Philosophy

1. **The LLM Never Sees Data Values**: Local LLMs (Ollama `llama3.2`) act strictly as translators from natural language into structured JSON query specifications. The model never receives raw observations, profile measurements, or statistical summaries.
2. **All Numbers Come From Code**: Statistical answers and summaries are generated from deterministic code templates.
3. **Explicit Quality Control & Modes**: Every query operates under an explicit data delivery mode (`research`, `standard`, or `expert`) and records full QC audit statistics.
4. **Reproducibility First**: Every completed query persists an immutable `QueryCard` with SHA-256 canonical data hashes, environment versions, and an auto-generated standalone Python reproduction script.

---

## 2. Architecture & Data Flow

```
                           +----------------------+
                           | Natural Language     |
                           | User Question        |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           | Intent Router        |
                           | (src/siqva/router.py)|
                           +----------+-----------+
                                      |
         +----------------------------+----------------------------+
         |                            |                            |
         v                            v                            v
  [GLOSSARY QUERY]            [DATA_FETCH QUERY]          [NUMERICAL OPERATION]
  (src/siqva/glossary.py)     (src/siqva/parser.py)       (src/siqva/operations.py)
         |                            |                            |
         |                            v                            |
         |                   +------------------+                  |
         |                   | Spec Validator   |                  |
         |                   | & Cost Cap Guard |                  |
         |                   +--------+---------+                  |
         |                            |                            |
         |                            v                            |
         |                   +------------------+                  |
         |                   | Multi-Month      |                  |
         |                   | Calendar Chunking|                  |
         |                   | (chunking.py)    |                  |
         |                   +--------+---------+                  |
         |                            |                            |
         |                            v                            |
         |                   +------------------+                  |
         |                   | argopy Fetcher   |                  |
         |                   | & Parquet Cache  |                  |
         |                   +--------+---------+                  |
         |                            |                            |
         |                            v                            |
         |                   +------------------+                  |
         |                   | QC Audit & Filter|                  |
         |                   | (src/siqva/qc.py)|                  |
         |                   +--------+---------+                  |
         |                            |                            |
         |                            v                            v
         |                   +------------------+       +---------------------+
         |                   | TEOS-10 Physics  |       | Deterministic Stats |
         |                   | (on-demand gsw)  |       | & Answer Templates  |
         |                   +--------+---------+       +----------+----------+
         |                            |                            |
         +----------------------------+----------------------------+
                                      |
                                      v
                           +----------------------+
                           | Plotly Graphs, Cards |
                           | & Streamlit UI       |
                           +----------------------+
```

---

## 3. Installation & Setup

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/) with `llama3.2` model (optional; system operates rules-first with zero external dependencies)

### Setup Virtual Environment
```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### Launch the Streamlit Web Application
```bash
streamlit run app/ui.py
```

### Run Benchmark Evaluation Harness
Evaluates question routing, parameter extraction, and parser-only latency against the internal developer test suite (`benchmark/questions.jsonl`).
> [!NOTE]
> This is a regression smoke test on 20 development questions written by the developers; not an independent evaluation. Latency reflects parser-only speed (rules path, no network, no data fetch).

```bash
python benchmark/run_eval.py
```

### Run Automated Pytest Suite
```bash
pytest -q
```

---

## 4. Key Capabilities

### Data Retrieval & Multi-Month Chunking
- **Single-Request Cost Cap**: Automatically enforces a 15,000 cost-unit cap ($\text{Area} \times \text{Days} \times [\text{Depth} / 500\text{ dbar}]$).
- **Calendar-Month Chunking**: Large multi-month queries exceeding 15,000 cost units are decomposed into monthly chunks up to `SIQVA_MAX_CHUNKS` (default 24).
- **Shared Monthly Caching**: Each monthly slice is fetched and stored independently in Parquet format, allowing overlapping queries to reuse cached months instantly.
- **Combined Deduplication**: Concatenated records are deduplicated by `(PLATFORM_NUMBER, CYCLE_NUMBER, PRES, TIME)` and capped by `SIQVA_MAX_TOTAL_ROWS` (default 3,000,000).

### On-Demand TEOS-10 Physical Oceanography
Physics calculations run strictly on-demand for physics intents using `gsw`:
- **`thermocline`**: Mixed Layer Depth (MLD), Isothermal Layer Depth (ILD), Barrier Layer Thickness (BLT), and 20 °C isotherm (Z20).
- **`tchp`**: Tropical Cyclone Heat Potential integrated down to the 26 °C isotherm (Z26).
- **`acoustic`**: TEOS-10 sound speed profile, Sonic Layer Depth (SLD), and deep SOFAR channel axis.

### Deterministic Numerical Operations (`operations.py`)
Answers statistical questions without LLM hallucinations:
- Aggregations: `mean`, `median`, `min`, `max`, `std`, `count`, `anomaly`.
- Vertical depth slicing and temporal grouping (`month`, `year`, `day`).
- Neutral template formatting with physical units (°C, PSU, dbar).

### Dual-Entity Comparison (`comparison.py`)
- Compares regions or time periods (e.g., *"compare Arabian Sea vs Bay of Bengal temperature in 2022"*).
- Reports exact numerical differences ($\Delta = A - B$) and profile counts without subjective claims (*"anomalous"*, *"abnormal"*, or *"unusual"*).

### Scientific Glossary (`glossary.py`)
- Provides exact, alias, and fuzzy lookup of oceanographic concepts.
- Definitions are loaded strictly from `data/glossary.json` with primary literature citations (e.g. de Boyer Montégut et al. 2004, Shay et al. 2000, Ewing & Worzel 1948).

### Conversational Follow-Ups & Multi-Session Privacy (`followup.py`)
- Supports conversational edits: *"same for salinity"*, *"now 2023"*, *"do it for Bay of Bengal"*.
- Session isolation controlled via `SIQVA_SHARED_HISTORY`: when set to `0`, query history is isolated per session ID.

### Cold Start & Cache Pre-Warming
- Dynamic seed query gallery loaded from `data/examples.json`.
- Non-blocking background thread (`warmup_ollama_async`) pings Ollama on startup to avoid UI stalls.
- Standalone pre-warming script: `scripts/warm_examples.py`.

---

## 5. Query Cards & Reproducibility

Every successful query produces a `QueryCard` containing:
- Cryptographic SHA-256 data hash computed from normalized observations.
- Execution environment metadata: `argopy` version, `xarray` version, fetch timestamp.
- Explicit data mode (`research`, `standard`, `expert`) and QC filter description.
- Standalone Python script reproducing the fetch and profile count verification.
- Re-run diffing comparing current data hashes against past fetches to detect delayed-mode updates.

---

## 6. Known Limitations

1. **Antimeridian Crossing (180°)**: Bounding boxes crossing the 180° meridian (where `lon_min > lon_max`) are rejected by the validator with an explicit message directing the user to split the query into eastern and western boxes.
2. **Water-Mass Classification**: Hardcoded Indian Ocean water-mass heuristics were permanently removed to prevent misleading classifications in other ocean basins.
3. **Core Argo Depth Scope**: Core physical variables (`TEMP`, `PSAL`, `PRES`) down to 2000 dbar are supported. Biogeochemical (BGC) and Deep Argo (>2000 dbar) are post-MVP scope.
4. **Float Index Snapshot**: Pre-fetch profile count ceilings strictly apply when the local index snapshot (`data/float_index.parquet`) provides full coverage; for partial or uncovered regions, the geometric cost cap guards the query and `profile_count_verified` is set to `False`.
