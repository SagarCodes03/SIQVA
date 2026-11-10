"""Tests for local float index (src/siqva/floatindex.py) and build_float_index.py."""

import json
from datetime import date, datetime, timezone
from pathlib import Path
import time
import numpy as np
import pandas as pd
import pytest

from siqva.floatindex import (
    CoverageStatus,
    FloatIndex,
    count_profiles,
    coverage_status,
    last_positions,
    load_float_index,
    query_profiles,
    snapshot_age_days,
    tracks,
)
from siqva.spec import BoundingBox, DateRange


@pytest.fixture
def sample_synthetic_index(tmp_path) -> FloatIndex:
    """Create a small synthetic FloatIndex with known coordinates, dates, and basins."""
    data = {
        "wmo": [10001, 10001, 10002, 10003, 10004],
        "cycle_number": [1, 2, 1, 1, 1],
        "cycle": [1, 2, 1, 1, 1],
        "latitude": [10.0, 11.0, -15.0, 0.0, 5.0],
        "longitude": [60.0, 61.0, 75.0, 175.0, -170.0],  # 10003 & 10004 near antimeridian
        "date": pd.to_datetime(["2022-01-05", "2022-01-15", "2022-02-01", "2022-03-01", "2022-03-10"]),
        "ocean": pd.Categorical(["I", "I", "I", "P", "P"]),
        "is_delayed": [True, True, False, True, False],
        "institution": ["AO", "AO", "IF", "IN", "IN"],
    }
    df = pd.DataFrame(data)
    meta = {
        "source_file": "synthetic.txt.gz",
        "build_date": "2026-01-01T00:00:00Z",
        "min_date": "2022-01-01",
        "max_date": "2022-12-31",
        "row_count": len(df),
        "dropped_row_count": 0,
    }
    parquet_path = tmp_path / "synthetic_index.parquet"
    json_path = tmp_path / "synthetic_index.json"

    df.to_parquet(parquet_path, index=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return FloatIndex(df=df, metadata=meta, parquet_path=parquet_path)


def test_missing_index_returns_unavailable_without_crash(tmp_path):
    """Proves load_float_index handles missing index files safely without raising."""
    idx = load_float_index(tmp_path / "non_existent.parquet")
    assert not idx.is_available
    assert idx.count_profiles() == 0
    assert idx.query_profiles().empty
    assert idx.last_positions().empty
    assert idx.tracks().empty
    assert idx.coverage_status(DateRange(start="2022-01-01", end="2022-01-10")) == CoverageStatus.NOT_COVERED
    assert idx.snapshot_age_days() is None


def test_query_profiles_standard_bbox(sample_synthetic_index):
    """Verify normal bounding box spatial filtering."""
    idx = sample_synthetic_index
    # Box covering WMO 10001 (lat 10..12, lon 59..62)
    bbox = BoundingBox(lon_min=59.0, lon_max=62.0, lat_min=9.0, lat_max=12.0)
    res = idx.query_profiles(bbox)
    assert len(res) == 2
    assert set(res["wmo"]) == {10001}


def test_query_profiles_antimeridian_bbox(sample_synthetic_index):
    """Verify antimeridian-crossing box (lon_min > lon_max) filters two ranges correctly."""
    idx = sample_synthetic_index
    # Antimeridian box crossing 180: from 170E (170) to 160W (-160)
    # Profiles: 10003 is at lon 175.0, 10004 is at lon -170.0
    res = idx.query_profiles(bbox_or_basin=(170.0, -160.0, -10.0, 10.0))
    assert len(res) == 2
    assert set(res["wmo"]) == {10003, 10004}


def test_query_profiles_basin_filtering(sample_synthetic_index):
    """Verify ocean basin string lookup (Indian, Pacific, Atlantic)."""
    idx = sample_synthetic_index
    indian = idx.query_profiles("Indian Ocean")
    assert len(indian) == 3
    assert set(indian["ocean"]) == {"I"}

    pacific = idx.query_profiles("Pacific Ocean")
    assert len(pacific) == 2
    assert set(pacific["ocean"]) == {"P"}

    atlantic = idx.query_profiles("Atlantic Ocean")
    assert len(atlantic) == 0


def test_query_profiles_date_range_and_delayed(sample_synthetic_index):
    """Verify temporal filtering and delayed_only flag."""
    idx = sample_synthetic_index
    # Jan 2022 only
    jan_res = idx.query_profiles(date_range=DateRange(start="2022-01-01", end="2022-01-31"))
    assert len(jan_res) == 2

    # Delayed only
    delayed_res = idx.query_profiles(delayed_only=True)
    assert len(delayed_res) == 3
    assert all(delayed_res["is_delayed"])


def test_last_positions(sample_synthetic_index):
    """Verify last_positions returns exactly one row per float with latest observation."""
    idx = sample_synthetic_index
    lp = idx.last_positions()
    # 4 distinct floats: 10001, 10002, 10003, 10004
    assert len(lp) == 4
    # For float 10001, cycle 2 was on 2022-01-15 (latest)
    f10001 = lp[lp["wmo"] == 10001].iloc[0]
    assert f10001["cycle_number"] == 2
    assert f10001["latitude"] == 11.0


def test_tracks(sample_synthetic_index):
    """Verify tracks returns positions chronologically sorted by wmo and date."""
    idx = sample_synthetic_index
    tr = idx.tracks()
    assert len(tr) == 5
    f10001 = tr[tr["wmo"] == 10001]
    assert list(f10001["cycle_number"]) == [1, 2]


def test_coverage_status(sample_synthetic_index):
    """Verify coverage_status returns FULL, PARTIAL, or NOT_COVERED."""
    idx = sample_synthetic_index
    # Index spans 2022-01-01 to 2022-12-31

    # Completely inside
    assert idx.coverage_status(DateRange(start="2022-05-01", end="2022-06-01")) == CoverageStatus.FULL

    # Overlaps but extends past max_date
    assert idx.coverage_status(DateRange(start="2022-11-01", end="2023-02-01")) == CoverageStatus.PARTIAL

    # Completely outside
    assert idx.coverage_status(DateRange(start="2025-01-01", end="2025-02-01")) == CoverageStatus.NOT_COVERED


def test_snapshot_age_days(sample_synthetic_index):
    """Verify snapshot age computation in days."""
    idx = sample_synthetic_index
    age = idx.snapshot_age_days(today=date(2026, 1, 11))
    # build_date is 2026-01-01 -> age = 10 days
    assert age == 10


def test_large_3m_synthetic_index_query_speed():
    """Benchmark query speed on an in-memory 3,000,000-row synthetic float index.

    Demonstrates query performance for S1 requirements.
    """
    n_rows = 3_000_000
    np.random.seed(42)

    # Fast generation of 3M rows
    wmos = np.random.randint(1000000, 7000000, size=n_rows, dtype=np.int32)
    cycles = np.random.randint(1, 250, size=n_rows, dtype=np.int32)
    lats = np.random.uniform(-80.0, 80.0, size=n_rows).astype(np.float32)
    lons = np.random.uniform(-180.0, 180.0, size=n_rows).astype(np.float32)
    is_delayed = np.random.choice([True, False], size=n_rows)
    oceans = np.random.choice(["A", "I", "P"], size=n_rows)

    # Random dates in 2020..2024
    start_ts = pd.Timestamp("2020-01-01").value // 10**9
    end_ts = pd.Timestamp("2024-12-31").value // 10**9
    rand_ts = np.random.randint(start_ts, end_ts, size=n_rows)
    dates = pd.to_datetime(rand_ts, unit="s")

    df_3m = pd.DataFrame(
        {
            "wmo": wmos,
            "cycle_number": cycles,
            "cycle": cycles,
            "latitude": lats,
            "longitude": lons,
            "date": dates,
            "ocean": pd.Categorical(oceans, categories=["A", "I", "P"]),
            "is_delayed": is_delayed,
        }
    )

    meta = {
        "build_date": "2026-11-10T12:00:00Z",
        "min_date": "2020-01-01",
        "max_date": "2024-12-31",
        "row_count": n_rows,
    }

    idx = FloatIndex(df=df_3m, metadata=meta)

    # Benchmark spatial + temporal query
    t0 = time.perf_counter()
    res = idx.query_profiles(
        bbox_or_basin=(50.0, 75.0, 5.0, 25.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
    )
    query_time_s = time.perf_counter() - t0

    # Benchmark count
    t1 = time.perf_counter()
    cnt = idx.count_profiles(
        bbox_or_basin=(50.0, 75.0, 5.0, 25.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
    )
    count_time_s = time.perf_counter() - t1

    # Assert correctness and sub-second speed
    assert cnt == len(res)
    assert query_time_s < 1.0, f"Query took {query_time_s:.3f}s (expected < 1.0s)"
    assert count_time_s < 1.0, f"Count took {count_time_s:.3f}s (expected < 1.0s)"
