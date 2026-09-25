# FloatChat — Testing Guide

## 1. Testing Strategy
| Type | Tool | What It Tests |
|---|---|---|
| Unit tests | pytest | Individual functions |
| Integration tests | pytest | Multiple modules together |
| Manual tests | Browser | Full end-to-end chat flow |
| Data validation | Custom | QC filter correctness |

---

## 2. Install Testing Tools
```bash
pip install pytest pytest-cov
```

---

## 3. Run Tests
```bash
# Run all tests
pytest tests/

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_qc_filter.py -v
```

---

## 4. Unit Tests

### test_qc_filter.py
```python
import pytest
import pandas as pd
from src.qc_filter import apply_qc_filter

def test_keeps_flag_1():
    """Flag 1 (good) data must always be kept"""
    df = pd.DataFrame({
        'TEMP': [25.0], 'TEMP_QC': [1],
        'PSAL': [35.0], 'PSAL_QC': [1],
        'PRES': [100.0], 'PRES_QC': [1]
    })
    result = apply_qc_filter(df)
    assert len(result) == 1

def test_keeps_flag_2():
    """Flag 2 (probably good) data must be kept"""
    df = pd.DataFrame({
        'TEMP': [25.0], 'TEMP_QC': [2],
        'PSAL': [35.0], 'PSAL_QC': [2],
        'PRES': [100.0], 'PRES_QC': [2]
    })
    result = apply_qc_filter(df)
    assert len(result) == 1

def test_drops_flag_3():
    """Flag 3 (probably bad) must be dropped"""
    df = pd.DataFrame({
        'TEMP': [25.0], 'TEMP_QC': [3],
        'PSAL': [35.0], 'PSAL_QC': [1],
        'PRES': [100.0], 'PRES_QC': [1]
    })
    result = apply_qc_filter(df)
    assert len(result) == 0

def test_drops_flag_4():
    """Flag 4 (bad data) must be dropped"""
    df = pd.DataFrame({
        'TEMP': [25.0], 'TEMP_QC': [4],
        'PSAL': [35.0], 'PSAL_QC': [4],
        'PRES': [100.0], 'PRES_QC': [4]
    })
    result = apply_qc_filter(df)
    assert len(result) == 0

def test_drops_flag_9():
    """Flag 9 (missing) must be dropped"""
    df = pd.DataFrame({
        'TEMP': [None], 'TEMP_QC': [9],
        'PSAL': [None], 'PSAL_QC': [9],
        'PRES': [100.0], 'PRES_QC': [9]
    })
    result = apply_qc_filter(df)
    assert len(result) == 0

def test_mixed_flags():
    """Mixed flags — only good rows kept"""
    df = pd.DataFrame({
        'TEMP': [25.0, 26.0, 27.0],
        'TEMP_QC': [1, 4, 2],
        'PSAL': [35.0, 35.1, 35.2],
        'PSAL_QC': [1, 1, 2],
        'PRES': [100, 200, 300],
        'PRES_QC': [1, 1, 1]
    })
    result = apply_qc_filter(df)
    assert len(result) == 2  # Row with flag 4 dropped
```

### test_validator.py
```python
from src.validator import is_ocean_query

def test_accepts_temperature_query():
    assert is_ocean_query("Show temperature in Bay of Bengal") == True

def test_accepts_salinity_query():
    assert is_ocean_query("What is salinity at 500m?") == True

def test_accepts_float_query():
    assert is_ocean_query("Show data for float WMO 2902795") == True

def test_rejects_weather_query():
    assert is_ocean_query("What is the weather in Mumbai today?") == False

def test_rejects_general_query():
    assert is_ocean_query("Who is the prime minister of India?") == False

def test_rejects_empty_query():
    assert is_ocean_query("") == False
```

### test_templates.py
```python
from src.templates import fill_template, select_template

def test_temp_by_region_template():
    params = {
        "lat_min": 8, "lat_max": 22,
        "lon_min": 80, "lon_max": 95,
        "date_start": "2023-01-01",
        "date_end": "2023-12-31"
    }
    query = fill_template("temp_by_region", params)
    assert "clean_measurements" in query
    assert "8" in query

def test_salinity_by_float_template():
    params = {"wmo_id": 2902795, "depth_min": 0, "depth_max": 500}
    query = fill_template("salinity_by_float", params)
    assert "2902795" in query

def test_no_raw_sql_in_output():
    """Template output must never contain DROP, DELETE, INSERT"""
    params = {"wmo_id": 123, "depth_min": 0, "depth_max": 100}
    query = fill_template("salinity_by_float", params)
    assert "DROP" not in query.upper()
    assert "DELETE" not in query.upper()
    assert "INSERT" not in query.upper()
```

---

## 5. Integration Tests

### test_pipeline.py
```python
def test_full_fetch_and_filter():
    """
    Integration test: fetch real data from Argovis
    and verify QC filter is applied
    """
    from src.fetcher import fetch_by_region
    from src.qc_filter import apply_qc_filter

    raw = fetch_by_region(
        lat_min=10, lat_max=15,
        lon_min=80, lon_max=85,
        date_start="2023-01-01",
        date_end="2023-01-10"
    )
    filtered = apply_qc_filter(raw)

    # Verify no bad flags remain
    assert not any(filtered['TEMP_QC'].isin([3, 4, 9]))
    assert not any(filtered['PSAL_QC'].isin([3, 4, 9]))

def test_rag_retrieval_returns_results():
    """RAG must return relevant chunks for ocean query"""
    from src.rag import retrieve_chunks
    chunks = retrieve_chunks("temperature Bay of Bengal 2023")
    assert len(chunks) > 0
    assert len(chunks) <= 5  # TOP_K = 5
```

---

## 6. Manual Test Cases (Run in Browser)

| # | Query | Expected Result |
|---|---|---|
| 1 | "Show temperature in Bay of Bengal 2023" | Depth profile chart + answer with WMO |
| 2 | "What is salinity for float 2902795" | Salinity profile + provenance card |
| 3 | "Show float positions in Arabian Sea" | Folium map with float markers |
| 4 | "What is the weather in Delhi?" | Rejection message |
| 5 | "sdkjfhsdf" | Rejection or clarification request |
| 6 | "Compare temperature at 100m and 500m" | Two-line chart comparison |
| 7 | Ask same query twice | Second response faster (cache hit) |
| 8 | Ask follow-up: "What about salinity?" | Uses session memory from prev query |

---

## 7. QC Validation Test (Key Proof)
Run this to prove our improvement works:
```python
# Show results WITH and WITHOUT QC filter
# Screenshot both — use as evidence in report

raw_count = len(raw_data)
filtered_count = len(apply_qc_filter(raw_data))
dropped = raw_count - filtered_count

print(f"Total measurements: {raw_count}")
print(f"After QC filter:    {filtered_count}")
print(f"Bad data dropped:   {dropped} ({dropped/raw_count*100:.1f}%)")
```
