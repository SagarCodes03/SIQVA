# SIQVA â€” Smart Interface of Query and Visualization of Argo data
*(formerly ArgoCard / FloatChat-R)*

SIQVA turns natural-language oceanographic questions into validated, QC-explicit query specifications, fetches real ocean observations via `argopy`, performs deterministic thermodynamic and TEOS-10 physical analysis (`gsw`), renders interactive visualizations (temperature & salinity profiles, T-S diagrams, trajectories, thermocline & barrier layer, cyclone heat potential, and underwater acoustic properties), and exports reproducible, verifiable **Query Cards**.

## Quickstart

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/) with `llama3.2` model (optional, for LLM fallback parsing)

### Installation
```bash
pip install -r requirements.txt
```

### Launch the Streamlit Web Application
```bash
streamlit run app/ui.py
```

### Run Tests
```bash
pytest
```
