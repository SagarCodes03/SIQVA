# FloatChat — Code Style Guide

## 1. Language & Version
- Python 3.10+
- Follow PEP 8 standard throughout

---

## 2. Naming Conventions
| Type | Convention | Example |
|---|---|---|
| Variables | snake_case | wmo_id, qc_flag, profile_date |
| Functions | snake_case | fetch_profiles(), apply_qc_filter() |
| Classes | PascalCase | FloatFetcher, QueryValidator |
| Constants | UPPER_SNAKE | GOOD_QC_FLAGS, MAX_DEPTH |
| Files | snake_case | qc_filter.py, chart_generator.py |

---

## 3. File Structure Rules
- Max 200 lines per file — split if longer
- One responsibility per file (single responsibility principle)
- All imports at top of file
- Group imports: standard library → third party → local

```python
# Standard library
import os
import json
from datetime import datetime

# Third party
import pandas as pd
import argopy
from langchain_community.llms import Ollama

# Local
from src.qc_filter import apply_qc_filter
from config.settings import Settings
```

---

## 4. Function Rules
- Max 30 lines per function — split if longer
- Every function must have a docstring
- Every function must have type hints

```python
def apply_qc_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter ARGO measurements to keep only good quality data.
    Keeps QC flags 1 (good) and 2 (probably good).
    Drops flags 3 (probably bad), 4 (bad), 9 (missing).

    Args:
        df: Raw ARGO DataFrame from argopy

    Returns:
        Filtered DataFrame with only valid measurements
    """
    GOOD_FLAGS = [1, 2]
    return df[
        df['TEMP_QC'].isin(GOOD_FLAGS) &
        df['PSAL_QC'].isin(GOOD_FLAGS) &
        df['PRES_QC'].isin(GOOD_FLAGS)
    ].copy()
```

---

## 5. Error Handling Rules
- Never use bare except — always specify exception type
- Always log errors before raising
- User-facing errors must be friendly messages

```python
# WRONG
try:
    data = fetch_profiles()
except:
    pass

# CORRECT
try:
    data = fetch_profiles()
except argopy.errors.DataNotFound as e:
    logger.error(f"No ARGO data found: {e}")
    return "No data found for this region and date range."
except ConnectionError as e:
    logger.error(f"API connection failed: {e}")
    return "Could not connect to ARGO data service. Please try again."
```

---

## 6. Logging Rules
- Use Python logging module — never use print() in production code
- Log levels: DEBUG for dev, INFO for operations, ERROR for failures

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Fetching profiles for region: %s", region)
logger.info("QC filter applied: %d rows kept of %d", kept, total)
logger.error("Database connection failed: %s", str(e))
```

---

## 7. Comments Rules
- Comment WHY not WHAT
- Every complex block must have a comment
- Always comment QC filter logic with flag meanings

```python
# WRONG
# Filter the dataframe
df = df[df['TEMP_QC'].isin([1, 2])]

# CORRECT
# Keep only scientifically valid measurements
# Flag 1 = good data, Flag 2 = probably good
# This is FloatChat's key improvement over existing systems
df = df[df['TEMP_QC'].isin([1, 2])]
```

---

## 8. Constants File (config/settings.py)
All magic numbers must be constants — never hardcode in logic

```python
# QC Flags
GOOD_QC_FLAGS = [1, 2]
BAD_QC_FLAGS = [3, 4, 9]

# ARGO Data Limits
MAX_DEPTH_DBAR = 2000
MIN_LAT = -90
MAX_LAT = 90
MIN_LON = -180
MAX_LON = 180

# RAG Settings
TOP_K_RESULTS = 5
MAX_CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# Cache
CACHE_TTL_HOURS = 24

# LLM
MAX_TOKENS = 1000
TEMPERATURE = 0.1   # Low temp = more factual, less creative
```

---

## 9. Git Commit Style
```
feat: add QC flag filtering to fetcher pipeline
fix: correct salinity template parameter order
docs: update architecture.md with layer 5 details
test: add unit tests for qc_filter.py
refactor: split etl.py into fetch and transform modules
```
