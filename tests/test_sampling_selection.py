"""Tests for deterministic sample selection (Task S5: floatindex.select_sample)."""

from datetime import date
import numpy as np
import pandas as pd
import pytest

from siqva.floatindex import (
    FloatIndex,
    SamplePick,
    SampleSelection,
    SAMPLE_DEFAULT,
    SAMPLE_MAX,
    SAMPLE_STEPS,
    compute_sample_seed,
    select_sample,
)
from siqva.spec import BoundingBox, DataMode, DateRange, QuerySpec, Variable, Intent


@pytest.fixture
def rich_synthetic_index(tmp_path) -> FloatIndex:
    """Create a synthetic FloatIndex with 100 profiles across 10 floats, 4 months, and 2 basins."""
    wmos = [2901000 + i for i in range(10)]
    records = []
    base_dates = pd.date_range("2022-01-01", "2022-04-30", periods=10)

    for i, wmo in enumerate(wmos):
        # Place floats across Arabian Sea / Indian Ocean (lat 10..20, lon 60..75)
        # and two floats near the antimeridian (lat -5..5, lon 175..185 aka -175)
        is_anti = i >= 8
        base_lat = 0.0 if is_anti else 10.0 + (i % 4) * 3.0
        base_lon = (175.0 if i == 8 else -175.0) if is_anti else 60.0 + (i % 4) * 4.0
        ocean = "P" if is_anti else "I"

        for cycle in range(1, 11):
            dt = base_dates[(cycle - 1) % len(base_dates)] + pd.Timedelta(days=i)
            # Cycles 1..7 delayed, 8..10 real-time
            is_del = cycle <= 7
            records.append({
                "wmo": wmo,
                "cycle": cycle,
                "cycle_number": cycle,
                "latitude": base_lat + (cycle * 0.1),
                "longitude": base_lon + (cycle * 0.1),
                "date": dt,
                "ocean": ocean,
                "is_delayed": is_del,
                "institution": "AO" if i % 2 == 0 else "IN",
            })

    df = pd.DataFrame(records)
    meta = {
        "build_date": "2026-01-01T00:00:00Z",
        "min_date": "2022-01-01",
        "max_date": "2022-05-15",
        "row_count": len(df),
    }
    return FloatIndex(df=df, metadata=meta, parquet_path=tmp_path / "test_idx.parquet")


def test_constants_defined():
    """Verify named constants required by design point 3."""
    assert SAMPLE_DEFAULT == 12
    assert SAMPLE_STEPS == (12, 24, 48)
    assert SAMPLE_MAX == 50


def test_sample_pick_structure():
    """Verify SamplePick attributes, typing, and immutability."""
    p = SamplePick(wmo=2901234, cycle=5, date="2022-01-15", lat=12.3456, lon=65.4321, is_delayed=True)
    assert p.wmo == 2901234
    assert p.cycle == 5
    assert p.date == "2022-01-15"
    assert p.lat == 12.3456
    assert p.lon == 65.4321
    assert p.is_delayed is True
    # Can unpack or access like tuple
    assert p[0] == 2901234
    assert p[1] == 5


def test_determinism(rich_synthetic_index):
    """Calling select_sample twice with the same inputs produces identical picks in identical order."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    res1 = rich_synthetic_index.select_sample(box, dr, n=8, fetch_key="test_key_1", mode="research")
    res2 = rich_synthetic_index.select_sample(box, dr, n=8, fetch_key="test_key_1", mode="research")

    assert len(res1.picks) == 8
    assert len(res2.picks) == 8
    assert res1.seed == res2.seed
    assert res1.picks == res2.picks

    # Different fetch_key yields different seed
    res3 = rich_synthetic_index.select_sample(box, dr, n=8, fetch_key="different_key", mode="research")
    assert res1.seed != res3.seed


def test_distinct_floats_preferred(rich_synthetic_index):
    """Verify distinct floats are preferred when selecting a sample."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    # In our fixture there are 8 floats in this box
    res = rich_synthetic_index.select_sample(box, dr, n=8, mode="standard")
    assert len(res.picks) == 8
    unique_wmos = {p.wmo for p in res.picks}
    # Exactly 8 distinct floats chosen
    assert len(unique_wmos) == 8


def test_spread_space_and_time(rich_synthetic_index):
    """Verify selected sample spans multiple time intervals and latitudes."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    res = rich_synthetic_index.select_sample(box, dr, n=12, mode="standard")
    assert len(res.picks) == 12

    dates = [p.date for p in res.picks]
    lats = [p.lat for p in res.picks]

    # Check temporal spread (min date in Jan, max date in March/April)
    assert min(dates) < "2022-02-01"
    assert max(dates) > "2022-03-01"

    # Check spatial spread
    assert max(lats) - min(lats) > 5.0


def test_one_profile_per_cell_slice(rich_synthetic_index):
    """Verify that initial selection round assigns at most one profile per cell/slice."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    # Request small n so it easily fits within non-empty bins in round 1
    res = rich_synthetic_index.select_sample(box, dr, n=4, mode="standard")
    assert len(res.picks) == 4
    # All 4 picks should be distinct floats
    unique_wmos = {p.wmo for p in res.picks}
    assert len(unique_wmos) == 4


def test_delayed_mode_filter(rich_synthetic_index):
    """In research mode only is_delayed == True profiles are selected; standard allows all."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    res_res = rich_synthetic_index.select_sample(box, dr, n=12, mode="research")
    assert all(p.is_delayed for p in res_res.picks)

    # Standard mode can include real-time profiles
    res_std = rich_synthetic_index.select_sample(box, dr, n=12, mode="standard")
    # Verify both can be returned
    assert len(res_std.picks) == 12


def test_delayed_mode_fewer_than_n_warning(rich_synthetic_index):
    """When fewer delayed profiles exist than n, research mode returns available with warning."""
    # Narrow date range where only a few delayed profiles exist
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-01-06")

    res = rich_synthetic_index.select_sample(box, dr, n=12, mode="research")
    assert len(res.picks) < 12
    assert res.warning is not None
    assert "delayed-mode profiles available in research mode" in res.warning
    assert "standard mode" in res.warning


def test_antimeridian_crossing(rich_synthetic_index):
    """Verify sample selection across the 180° meridian (Pacific box)."""
    # Box from 170E (170.0) to 170W (-170.0)
    anti_box = BoundingBox(lon_min=170.0, lon_max=-170.0, lat_min=-10.0, lat_max=10.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    res = rich_synthetic_index.select_sample(anti_box, dr, n=6, mode="standard")
    assert len(res.picks) > 0
    # Both floats (10008 and 10009) should be picked
    wmos = {p.wmo for p in res.picks}
    assert 2901008 in wmos or 2901009 in wmos


def test_fewer_profiles_than_n(rich_synthetic_index):
    """When fewer profiles exist in region than n, return all available profiles."""
    box = BoundingBox(lon_min=55.0, lon_max=62.0, lat_min=5.0, lat_max=12.0)
    dr = DateRange(start="2022-01-01", end="2022-01-10")

    res = rich_synthetic_index.select_sample(box, dr, n=24, mode="standard")
    assert 0 < len(res.picks) < 24
    assert res.n_available == len(res.picks)
    assert f"Selected all {len(res.picks)} available profiles" in res.method


def test_empty_region(rich_synthetic_index):
    """When 0 profiles match, returns empty list with no crash."""
    box = BoundingBox(lon_min=0.0, lon_max=5.0, lat_min=0.0, lat_max=5.0)
    dr = DateRange(start="2022-01-01", end="2022-01-10")

    res = rich_synthetic_index.select_sample(box, dr, n=12)
    assert len(res.picks) == 0
    assert res.n_available == 0
    assert "No matching profiles found" in res.method


def test_cap_sample_max(rich_synthetic_index):
    """Requested n > SAMPLE_MAX is capped at 50."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    res = rich_synthetic_index.select_sample(box, dr, n=100, mode="standard")
    assert len(res.picks) <= SAMPLE_MAX
    assert res.n_requested == 100


def test_unpacking_support(rich_synthetic_index):
    """Verify that SampleSelection unpacks as (picks, method)."""
    box = BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0)
    dr = DateRange(start="2022-01-01", end="2022-04-30")

    picks, method = rich_synthetic_index.select_sample(box, dr, n=6, mode="standard")
    assert isinstance(picks, list)
    assert isinstance(method, str)
    assert len(picks) == 6


def test_query_spec_direct_invocation(rich_synthetic_index):
    """Verify select_sample accepts a QuerySpec object directly."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=55.0, lon_max=80.0, lat_min=5.0, lat_max=25.0),
        date_range=DateRange(start="2022-01-01", end="2022-04-30"),
        variables=[Variable.TEMP],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    res = rich_synthetic_index.select_sample(spec, n=8)
    assert len(res.picks) == 8
    assert all(p.is_delayed for p in res.picks)

