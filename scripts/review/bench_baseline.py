"""
scripts/review/bench_baseline.py

Honest, offline benchmark of SIQVA pipeline stages on:
1. Fixed test fixture (tests/fixtures/sample_argo_standard.parquet)
2. Largest cached Parquet in cache/ (if any)

Measures:
- Cold (first invocation) and Warm (median of 3 passes) timings using time.perf_counter()
- Memory pass conducted separately afterwards (never during timing passes)
- Detailed figure stats: traces, total points, to_json() serialization size (KB) and serialization time
- Mocked pipeline.run timing with zero network calls
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import tracemalloc
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Ensure src is on sys.path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from siqva.analyzer import analyze
from siqva.card import build_card, list_cards, restore_card_result, save_card
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.parser import parse_detailed
from siqva.physics import compute_new_features
from siqva.pipeline import run
from siqva.plots import (
    plot_acoustic_profile,
    plot_cyclone_tchp,
    plot_depth_profile,
    plot_position_map,
    plot_thermocline_and_barrier,
    plot_ts_diagram,
)
from siqva.qc import audit_qc
from siqva.spec import DataMode, DepthRange, Intent, QuerySpec, Variable
from siqva.validator import validate_spec


def load_datasets() -> tuple[pd.DataFrame, Path, pd.DataFrame, Path]:
    fixture_path = ROOT / "tests" / "fixtures" / "sample_argo_standard.parquet"
    if not fixture_path.exists():
        fixture_path = ROOT / "tests" / "fixtures" / "sample_argo_expert.parquet"
    df_fixture = pd.read_parquet(fixture_path)

    cache_dir = ROOT / "cache"
    cache_parquets = list(cache_dir.glob("*.parquet"))
    if cache_parquets:
        largest_cache_path = max(cache_parquets, key=lambda p: p.stat().st_size)
        df_cache = pd.read_parquet(largest_cache_path)
    else:
        largest_cache_path = fixture_path
        df_cache = df_fixture

    return df_fixture, fixture_path, df_cache, largest_cache_path


def get_fig_stats(fig: go.Figure) -> dict[str, Any]:
    traces = len(fig.data)
    points = 0
    for tr in fig.data:
        if hasattr(tr, "x") and tr.x is not None:
            points += len(tr.x)
        elif hasattr(tr, "lat") and tr.lat is not None:
            points += len(tr.lat)
        elif hasattr(tr, "values") and tr.values is not None:
            points += len(tr.values)

    t0 = time.perf_counter()
    js = fig.to_json()
    t_json = time.perf_counter() - t0
    size_kb = len(js.encode("utf-8")) / 1024.0

    return {
        "traces": traces,
        "points": points,
        "size_kb": size_kb,
        "json_time_ms": t_json * 1000.0,
    }


def run_benchmark_suite(df: pd.DataFrame, dataset_path: Path, label: str) -> dict[str, Any]:
    row_count = len(df)
    col_count = len(df.columns)
    unique_profiles = df["PLATFORM_NUMBER"].nunique() if "PLATFORM_NUMBER" in df.columns else 1

    print(f"\n================================================================================")
    print(f"BENCHMARKING DATASET: {label}")
    print(f"File: {dataset_path.name} | Rows: {row_count:,} | Columns: {col_count} | Unique Floats: {unique_profiles}")
    print(f"================================================================================")

    question = "temperature and salinity in the Arabian Sea between 2022-01-01 and 2022-01-10"

    # Pre-parse spec for reuse
    parsed_res = parse_detailed(question, today=date(2026, 11, 10))
    spec = parsed_res.spec
    fetch_key = spec.fetch_key()

    # Create FetchResult with mock metadata
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-10T00:00:00Z",
        row_count=row_count,
        profile_count=unique_profiles,
        data_hash="bench_hash",
        fetch_key=fetch_key,
    )
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=True,
        cache_key=fetch_key,
        metadata=meta,
        effective_depth_range=spec.depth_range or DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=unique_profiles,
    )

    # 3 timing passes without memory profiling
    stages = [
        "1. Parse (rules)",
        "2. Validate spec",
        "3. Cache Load (parquet read)",
        "4. QC Audit",
        "5. Analyze",
        "6. Plot: Map (plot_position_map)",
        "7. Plot: Profile (plot_depth_profile)",
        "8. Plot: T-S (plot_ts_diagram)",
        "9. Physics Calc (All intents)",
        "10. Plot: Thermocline (plot_thermocline_and_barrier)",
        "11. Plot: TCHP (plot_cyclone_tchp)",
        "12. Plot: Acoustic (plot_acoustic_profile)",
        "13. Card Build",
        "14. SQLite Save Card",
        "15. History List (list_cards)",
        "16. History Restore (restore_card_result)",
        "17. Total Pipeline.run (mocked fetch)",
    ]

    raw_timings: dict[str, list[float]] = {st: [] for st in stages}
    captured_figs: dict[str, go.Figure] = {}

    for pass_idx in range(3):
        # 1. Parse
        t0 = time.perf_counter()
        _ = parse_detailed(question, today=date(2026, 11, 10))
        raw_timings["1. Parse (rules)"].append(time.perf_counter() - t0)

        # 2. Validate
        t0 = time.perf_counter()
        validate_spec(spec)
        raw_timings["2. Validate spec"].append(time.perf_counter() - t0)

        # 3. Cache Load
        t0 = time.perf_counter()
        _ = pd.read_parquet(dataset_path)
        raw_timings["3. Cache Load (parquet read)"].append(time.perf_counter() - t0)

        # 4. QC Audit
        t0 = time.perf_counter()
        _ = audit_qc(df, spec.variables, spec.mode)
        raw_timings["4. QC Audit"].append(time.perf_counter() - t0)

        # 5. Analyze
        t0 = time.perf_counter()
        analysis_res = analyze(df, spec, fetch_res)
        raw_timings["5. Analyze"].append(time.perf_counter() - t0)

        # 6. Plot Map
        t0 = time.perf_counter()
        fig_map = plot_position_map(df)
        raw_timings["6. Plot: Map (plot_position_map)"].append(time.perf_counter() - t0)
        captured_figs["Map"] = fig_map

        # 7. Plot Profile
        t0 = time.perf_counter()
        fig_prof = plot_depth_profile(df, variable=Variable.TEMP)
        raw_timings["7. Plot: Profile (plot_depth_profile)"].append(time.perf_counter() - t0)
        captured_figs["Profile"] = fig_prof

        # 8. Plot T-S
        t0 = time.perf_counter()
        fig_ts = plot_ts_diagram(df)
        raw_timings["8. Plot: T-S (plot_ts_diagram)"].append(time.perf_counter() - t0)
        captured_figs["T-S"] = fig_ts

        # 9. Physics calculations
        t0 = time.perf_counter()
        df_phys, phys_summs = compute_new_features(df, intent=None)
        raw_timings["9. Physics Calc (All intents)"].append(time.perf_counter() - t0)

        rep_prof = phys_summs[0] if phys_summs else None

        # 10. Plot Thermocline
        t0 = time.perf_counter()
        fig_mld = plot_thermocline_and_barrier(df_phys, rep_prof)
        raw_timings["10. Plot: Thermocline (plot_thermocline_and_barrier)"].append(time.perf_counter() - t0)
        captured_figs["Thermocline"] = fig_mld

        # 11. Plot TCHP
        t0 = time.perf_counter()
        fig_tchp = plot_cyclone_tchp(df_phys, rep_prof)
        raw_timings["11. Plot: TCHP (plot_cyclone_tchp)"].append(time.perf_counter() - t0)
        captured_figs["TCHP"] = fig_tchp

        # 12. Plot Acoustic
        t0 = time.perf_counter()
        fig_acou = plot_acoustic_profile(df_phys, rep_prof)
        raw_timings["12. Plot: Acoustic (plot_acoustic_profile)"].append(time.perf_counter() - t0)
        captured_figs["Acoustic"] = fig_acou

        # 13. Card Build
        t0 = time.perf_counter()
        card = build_card(spec, fetch_res, analysis_res, question=question)
        raw_timings["13. Card Build"].append(time.perf_counter() - t0)

        # 14. SQLite Save & 15. List & 16. Restore
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            temp_db = Path(tf.name)
        try:
            t0 = time.perf_counter()
            save_card(card, db_path=temp_db)
            raw_timings["14. SQLite Save Card"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            _ = list_cards(db_path=temp_db)
            raw_timings["15. History List (list_cards)"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            # restore_card_result expects cache parquet at cache_dir
            _ = restore_card_result(card, cache_dir=dataset_path.parent)
            raw_timings["16. History Restore (restore_card_result)"].append(time.perf_counter() - t0)
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass

        # 17. Total pipeline.run with mocked fetch
        def mock_fetch_fn(s, **kwargs):
            return fetch_res

        t0 = time.perf_counter()
        _ = run(question=question, today=date(2026, 11, 10), fetcher_fn=mock_fetch_fn)
        raw_timings["17. Total Pipeline.run (mocked fetch)"].append(time.perf_counter() - t0)

    # Print Timing Table
    print(f"\n{'Stage':<45} | {'Cold (1st run)':<15} | {'Warm (Median)':<15}")
    print("-" * 80)
    for st in stages:
        cold = raw_timings[st][0]
        warm = float(np.median(raw_timings[st]))
        print(f"{st:<45} | {cold*1000:10.2f} ms   | {warm*1000:10.2f} ms")

    # Figure Stats Table
    print(f"\n--- Plot Figures Serialization & Trace Breakdown ({label}) ---")
    print(f"{'Plot Figure':<20} | {'Traces':<8} | {'Points':<10} | {'JSON Size (KB)':<15} | {'JSON Time (ms)':<15}")
    print("-" * 75)
    fig_stats_dict = {}
    for name, fig in captured_figs.items():
        stats = get_fig_stats(fig)
        fig_stats_dict[name] = stats
        print(f"{name:<20} | {stats['traces']:<8} | {stats['points']:<10} | {stats['size_kb']:12.2f} KB | {stats['json_time_ms']:12.2f} ms")

    # Separate Memory Pass
    print(f"\n--- Running Independent Memory Profiling Pass ({label}) ---")
    tracemalloc.start()
    tracemalloc.reset_peak()
    _ = analyze(df, spec, fetch_res)
    _ = plot_position_map(df)
    _ = plot_depth_profile(df, variable=Variable.TEMP)
    _ = plot_ts_diagram(df)
    df_p, p_sum = compute_new_features(df, intent=None)
    if p_sum:
        _ = plot_thermocline_and_barrier(df_p, p_sum[0])
        _ = plot_cyclone_tchp(df_p, p_sum[0])
        _ = plot_acoustic_profile(df_p, p_sum[0])
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Current Memory Allocated: {current_mem / (1024*1024):.2f} MB")
    print(f"Peak Memory Allocated:    {peak_mem / (1024*1024):.2f} MB")

    return {
        "row_count": row_count,
        "timings": raw_timings,
        "fig_stats": fig_stats_dict,
        "peak_mem_mb": peak_mem / (1024 * 1024),
    }


def main():
    df_fix, fix_path, df_cache, cache_path = load_datasets()

    print("SIQVA SPEED BASELINE & BENCHMARK")
    print("=" * 80)
    print("Python version:", sys.version)
    print("Fixture:", fix_path)
    print("Cache file:", cache_path)

    bench_fix = run_benchmark_suite(df_fix, fix_path, "FIXED FIXTURE")
    bench_cache = run_benchmark_suite(df_cache, cache_path, "LARGEST CACHE PARQUET")

    print("\nBENCHMARK COMPLETE.")


if __name__ == "__main__":
    main()
