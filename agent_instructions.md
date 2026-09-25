# FloatChat — Coding Agent Instructions
# Give this file to Cursor / Claude Code / any AI coding agent before starting

## What This Project Is
FloatChat is an AI-powered conversational interface for ARGO ocean data discovery and visualization. Users type plain English questions and get real ocean data answers with charts.

---

## What You Are Building
A Python + Streamlit web app with:
1. A chat UI where users ask ocean questions
2. A template-based NL query engine (NO raw NL2SQL)
3. Live data fetching from ARGO via argopy library
4. QC flag filtering (keep only flag 1 and 2 data)
5. RAG pipeline using ChromaDB + sentence-transformers
6. PostgreSQL storage for structured profile data
7. Ollama (Llama 3.2) as the local free LLM
8. Plotly charts auto-generated from query results

---

## Critical Rules — Never Break These

### Rule 1 — NO raw NL2SQL
Never let the LLM generate raw SQL. Always use pre-defined templates in templates.py. The LLM only extracts parameters and picks a template.

### Rule 2 — Always filter QC flags
Before storing or using ANY ARGO measurement, filter using qc_filter.py. Only keep flag 1 (good) and flag 2 (probably good). Drop 3, 4, 9.

### Rule 3 — Always show provenance
Every LLM answer must include: WMO number, latitude, longitude, date, QC status. Never show data without its source.

### Rule 4 — Use argopy for all data
Never hardcode ocean data. Never use static files. Always fetch via argopy DataFetcher connected to Argovis API.

### Rule 5 — Keep everything free
Do not use OpenAI API, Pinecone, or any paid service. Use Ollama, ChromaDB, PostgreSQL, sentence-transformers only.

---

## File Responsibilities
| File | What it does |
|---|---|
| app.py | Main Streamlit UI — entry point |
| src/validator.py | Checks if query is ocean-related |
| src/intent.py | LLM classifies query type |
| src/templates.py | 5 safe SQL query templates |
| src/fetcher.py | argopy data fetching |
| src/qc_filter.py | QC flag filtering |
| src/etl.py | xarray → Pandas → text chunks |
| src/rag.py | ChromaDB embed + retrieve |
| src/llm.py | Ollama LangChain wrapper |
| src/charts.py | Plotly + Folium chart generator |
| db/db.py | PostgreSQL connection + queries |
| db/schema.sql | Database table definitions |
| config/settings.py | All config from .env |

---

## 5 Safe Query Templates
```python
TEMPLATES = {
    "temp_by_region": "SELECT * FROM clean_measurements WHERE latitude BETWEEN {lat_min} AND {lat_max} AND longitude BETWEEN {lon_min} AND {lon_max} AND profile_date BETWEEN {date_start} AND {date_end}",
    "salinity_by_float": "SELECT * FROM clean_measurements WHERE wmo_id = {wmo_id} AND pressure BETWEEN {depth_min} AND {depth_max}",
    "profile_by_date": "SELECT * FROM clean_measurements WHERE DATE(profile_date) = {date} AND ST_DWithin(location, ST_MakePoint({lon},{lat}), {radius})",
    "float_trajectory": "SELECT profile_date, latitude, longitude FROM profiles WHERE wmo_id = {wmo_id} AND profile_date BETWEEN {date_start} AND {date_end}",
    "param_by_depth": "SELECT * FROM clean_measurements WHERE pressure BETWEEN {depth_min} AND {depth_max} AND profile_date BETWEEN {date_start} AND {date_end}"
}
```

---

## QC Filter Code
```python
def apply_qc_filter(df):
    GOOD_FLAGS = [1, 2]
    return df[
        df['TEMP_QC'].isin(GOOD_FLAGS) &
        df['PSAL_QC'].isin(GOOD_FLAGS) &
        df['PRES_QC'].isin(GOOD_FLAGS)
    ]
```

---

## Chart Selection Logic
```python
def select_chart(intent):
    chart_map = {
        "depth_profile": "line_chart",
        "map": "scatter_geo",
        "time_series": "time_series",
        "ts_diagram": "scatter_plot",
        "trajectory": "map_animation"
    }
    return chart_map.get(intent, "line_chart")
```

---

## Testing Queries (Use These to Verify)
1. "Show temperature profile in Bay of Bengal"
2. "What is the salinity at 500m for float 2902795"
3. "Show all floats near the Arabian Sea in 2023"
4. "What is the mixed layer depth in the Indian Ocean"
5. "Tell me about the weather today" → should be rejected
