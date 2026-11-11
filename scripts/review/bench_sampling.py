"""
scripts/review/bench_sampling.py

Offline benchmark measuring performance of the SIQVA FloatIndex and sampling subsystems
on a synthetic 3,000,000-row Argo float index.

Measures:
1. FloatIndex initialization / memory footprint.
2. Spatial-temporal query filtering (Bounding box query & Basin query).
3. Profile counting (count_profiles on box and basin).
4. Deterministic space-time sample selection (select_sample for N=12, 24, 48).
5. Overview map rendering (render_index_overview_map).

All passes run completely offline without touching the network or remote APIs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import gc
import os
from pathlib import Path
import sys
import time

# Ensure src is on sys.path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd

from siqva.floatindex import FloatIndex, SampleSelection
from siqva.plots import render_index_overview_map
from siqva.spec import BoundingBox, DateRange, Intent, QuerySpec, Variable


def generate_synthetic_index(n_rows: int = 3_000_000, seed: int = 42) -> pd.DataFrame:
    """Generate a realistic synthetic Argo float index DataFrame with n_rows."""
    print(f"Generating synthetic float index with {n_rows:,} rows (seed={seed})...")
    rng = np.random.default_rng(seed)

    # 15,000 unique WMOs
    wmos = rng.integers(1900000, 7900000, size=n_rows, dtype=np.int64)
    cycles = rng.integers(1, 300, size=n_rows, dtype=np.int32)
    lats = rng.uniform(-65.0, 65.0, size=n_rows).astype(np.float64)
    lons = rng.uniform(-180.0, 180.0, size=n_rows).astype(np.float64)

    # Dates spanning 2018-01-01 to 2024-12-31 (in seconds)
    start_ts = int(datetime(2018, 1, 1).timestamp())
    end_ts = int(datetime(2024, 12, 31).timestamp())
    random_ts = rng.integers(start_ts, end_ts, size=n_rows)
    dates = pd.to_datetime(random_ts, unit="s")

    # Oceans: P (55%), A (28%), I (17%)
    oceans = rng.choice(["P", "A", "I"], size=n_rows, p=[0.55, 0.28, 0.17])
    is_delayed = rng.choice([True, False], size=n_rows, p=[0.75, 0.25])
    institutions = rng.choice(["AO", "IN", "CS", "IF", "JA"], size=n_rows)

    df = pd.DataFrame(
        {
            "wmo": wmos,
            "cycle_number": cycles,
            "cycle": cycles,
            "latitude": lats,
            "longitude": lons,
            "date": dates,
            "ocean": oceans,
            "is_delayed": is_delayed,
            "institution": institutions,
        }
    )
    return df


def time_callable(fn, n_runs: int = 3) -> tuple[float, any]:
    """Execute fn n_runs times and return (median_time_ms, last_result)."""
    times = []
    res = None
    for _ in range(n_runs):
        gc.disable()
        t0 = time.perf_counter()
        res = fn()
        t1 = time.perf_counter()
        gc.enable()
        times.append((t1 - t0) * 1000.0)
    return float(np.median(times)), res


def main() -> None:
    print("=" * 70)
    print("SIQVA FloatIndex & Sampling Performance Benchmark")
    print("=" * 70)

    # 1. Generate synthetic index
    t0 = time.perf_counter()
    df = generate_synthetic_index(3_000_000)
    gen_time = time.perf_counter() - t0
    mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
    print(f"Generated {len(df):,} rows in {gen_time:.2f}s (RAM: {mem_mb:.1f} MB)")

    metadata = {
        "build_date": "2024-06-01T00:00:00Z",
        "min_date": "2018-01-01",
        "max_date": "2024-12-31",
        "total_profiles": len(df),
    }

    t0 = time.perf_counter()
    index = FloatIndex(df=df, metadata=metadata)
    init_time_ms = (time.perf_counter() - t0) * 1000.0
    print(f"FloatIndex wrapper initialized in {init_time_ms:.2f} ms")
    print("-" * 70)

    results = []

    # Test cases
    bbox_arabian = BoundingBox(lon_min=60.0, lon_max=75.0, lat_min=10.0, lat_max=25.0)
    dates_2023 = DateRange(start=date(2023, 1, 1), end=date(2023, 12, 31))

    # 2. Query Profiles - Bounding Box
    t_box_query, df_box = time_callable(
        lambda: index.query_profiles(bbox_or_basin=bbox_arabian, date_range=dates_2023)
    )
    print(f"[1] query_profiles (Bbox Arabian Sea, 1 year): {t_box_query:.2f} ms ({len(df_box):,} rows)")
    results.append(("query_profiles (Bbox, 1 year)", f"{t_box_query:.2f} ms", f"{len(df_box):,} matches"))

    # 3. Query Profiles - Basin
    t_basin_query, df_basin = time_callable(
        lambda: index.query_profiles(bbox_or_basin="indian ocean", date_range=dates_2023)
    )
    print(f"[2] query_profiles (Basin Indian Ocean, 1 year): {t_basin_query:.2f} ms ({len(df_basin):,} rows)")
    results.append(("query_profiles (Basin, 1 year)", f"{t_basin_query:.2f} ms", f"{len(df_basin):,} matches"))

    # 4. Count Profiles
    t_count_box, count_box = time_callable(
        lambda: index.count_profiles(bbox_or_basin=bbox_arabian, date_range=dates_2023)
    )
    print(f"[3] count_profiles (Bbox): {t_count_box:.2f} ms (count = {count_box:,})")
    results.append(("count_profiles (Bbox)", f"{t_count_box:.2f} ms", f"{count_box:,}"))

    t_count_basin, count_basin = time_callable(
        lambda: index.count_profiles(bbox_or_basin="indian ocean", date_range=dates_2023)
    )
    print(f"[4] count_profiles (Basin): {t_count_basin:.2f} ms (count = {count_basin:,})")
    results.append(("count_profiles (Basin)", f"{t_count_basin:.2f} ms", f"{count_basin:,}"))

    # 5. Deterministic Sample Selection (select_sample)
    for n in (12, 24, 48):
        t_sample, selection = time_callable(
            lambda n=n: index.select_sample(
                bbox_or_basin="indian ocean",
                date_range=dates_2023,
                n=n,
                fetch_key="bench_test_key_sample",
            )
        )
        print(f"[5] select_sample (N={n}, Basin): {t_sample:.2f} ms (picked {len(selection.picks)}, method={selection.method})")
        results.append((f"select_sample (N={n}, Basin)", f"{t_sample:.2f} ms", f"{len(selection.picks)} picks"))

    # 6. Overview Map Rendering (render_index_overview_map)
    spec_sample = QuerySpec(
        basin="Indian Ocean",
        date_range=dates_2023,
        variables=[Variable.TEMP],
        depth_range=(0.0, 500.0),
        intent=Intent.PROFILE,
    )
    t_map, (fig, pct, note) = time_callable(
        lambda: render_index_overview_map(index, spec_sample, max_tracks=15, max_markers=400)
    )
    print(f"[6] render_index_overview_map: {t_map:.2f} ms (traces={len(fig.data)})")
    results.append(("render_index_overview_map", f"{t_map:.2f} ms", f"{len(fig.data)} traces"))

    print("-" * 70)
    print(f"{'Operation':<35} | {'Median Time':<15} | {'Details'}")
    print("-" * 70)
    for op, elapsed, detail in results:
        print(f"{op:<35} | {elapsed:<15} | {detail}")
    print("=" * 70)

    # Save output to scripts/review/bench_sampling_out.txt
    out_file = ROOT / "scripts" / "review" / "bench_sampling_out.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("SIQVA FloatIndex & Sampling Performance Benchmark (3,000,000 rows)\n")
        f.write("=" * 70 + "\n")
        f.write(f"Generated Index Rows: {len(df):,} | RAM: {mem_mb:.1f} MB\n")
        f.write(f"Index Init: {init_time_ms:.2f} ms\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'Operation':<35} | {'Median Time':<15} | {'Details'}\n")
        f.write("-" * 70 + "\n")
        for op, elapsed, detail in results:
            f.write(f"{op:<35} | {elapsed:<15} | {detail}\n")
        f.write("=" * 70 + "\n")
    print(f"Results successfully saved to {out_file.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
