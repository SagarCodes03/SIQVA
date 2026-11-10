"""
scripts/review/bench_pipeline.py

Benchmark script to time each stage of SIQVA on fixed fixture data and the largest cached Parquet file.
Runs without modifying application source code.
"""

from __future__ import annotations

import cProfile
import io
import os
import pstats
import sys
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch

# Ensure src is in python path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
from siqva.analyzer import analyze
from siqva.card import build_card, list_cards, restore_card_result, save_card
from siqva.fetcher import FetchResult, FetchStatus
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


def load_datasets() -> tuple[pd.DataFrame, pd.DataFrame]:
    # 1. Test fixture
    fixture_path = ROOT / "tests" / "fixtures" / "sample_argo_expert.parquet"
    if fixture_path.exists():
        df_fixture = pd.read_parquet(fixture_path)
    else:
        # Fallback dummy dataframe
        df_fixture = pd.DataFrame({
            "PLATFORM_NUMBER": [1901234] * 50,
            "CYCLE_NUMBER": [1] * 50,
            "TIME": pd.date_range("2022-01-01", periods=50, freq="h"),
            "LATITUDE": [15.0] * 50,
            "LONGITUDE": [65.0] * 50,
            "PRES": [float(i * 10) for i in range(50)],
            "TEMP": [25.0 - i * 0.2 for i in range(50)],
            "PSAL": [35.0 + i * 0.01 for i in range(50)],
        })

    # 2. Largest cached parquet
    cache_dir = ROOT / "cache"
    parquets = list(cache_dir.glob("*.parquet"))
    if parquets:
        largest = max(parquets, key=lambda p: p.stat().st_size)
        print(f"Loaded largest cached parquet: {largest.name} ({largest.stat().st_size / 1024:.1f} KB)")
        df_cache = pd.read_parquet(largest)
    else:
        df_cache = df_fixture

    return df_fixture, df_cache


def time_stage(func, *args, **kwargs) -> tuple[float, any]:
    t0 = time.perf_counter()
    res = func(*args, **kwargs)
    t1 = time.perf_counter()
    return (t1 - t0), res


def run_benchmarks(df: pd.DataFrame, label: str):
    print(f"\n=======================================================")
    print(f"BENCHMARKING: {label} (Rows: {len(df):,})")
    print(f"=======================================================")

    question = "temperature in the Arabian Sea between 2022-01-01 and 2022-01-10"
    
    # 1. Parse
    t_parse, parse_outcome = time_stage(parse_detailed, question)
    spec: QuerySpec = parse_outcome.spec
    
    # 2. Validate
    t_val, _ = time_stage(validate_spec, spec)

    # Mock fetch result from df
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=True,
        cache_key=spec.fetch_key(),
        profile_count_verified=True,
        profile_count=df["PLATFORM_NUMBER"].nunique() if "PLATFORM_NUMBER" in df.columns else 1,
    )

    # 3. QC Audit
    t_qc, qc_report = time_stage(audit_qc, df, spec.variables, spec.mode)

    # 4. Analyze
    t_ana, analysis_res = time_stage(analyze, df, spec, fetch_res)

    # 5. Physics (thermocline, tchp, acoustic)
    t_phys_mld, (df_mld, phys_mld_list) = time_stage(compute_new_features, df, Intent.THERMOCLINE.value)
    t_phys_tchp, (df_tchp, phys_tchp_list) = time_stage(compute_new_features, df, Intent.TCHP.value)
    t_phys_acou, (df_acou, phys_acou_list) = time_stage(compute_new_features, df, Intent.ACOUSTIC.value)

    # 6. Plotting
    t_plot_prof, _ = time_stage(plot_depth_profile, df, "TEMP")
    t_plot_ts, _ = time_stage(plot_ts_diagram, df)
    t_plot_map, _ = time_stage(plot_position_map, df)
    
    first_mld = phys_mld_list[0] if phys_mld_list else None
    first_tchp = phys_tchp_list[0] if phys_tchp_list else None
    first_acou = phys_acou_list[0] if phys_acou_list else None

    t_plot_mld, _ = time_stage(plot_thermocline_and_barrier, df_mld, first_mld)
    t_plot_tchp, _ = time_stage(plot_cyclone_tchp, df_tchp, first_tchp)
    t_plot_acou, _ = time_stage(plot_acoustic_profile, df_acou, first_acou)

    # 7. Card build & SQLite save
    t_card, card = time_stage(build_card, spec, fetch_res, analysis_res, question=question)
    
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        temp_db = Path(tf.name)
    try:
        t_save, _ = time_stage(save_card, card, db_path=temp_db)
        t_list, _ = time_stage(list_cards, db_path=temp_db)
        t_restore, _ = time_stage(restore_card_result, card)
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except Exception:
            pass

    # 8. Total pipeline run (with fetch mocked to instantaneous memory load)
    with patch("siqva.pipeline.fetch", return_value=fetch_res):
        t_pipeline, pipe_res = time_stage(run, question=question)

    results = {
        "1. Parse (rules)": t_parse,
        "2. Validate spec": t_val,
        "3. QC audit": t_qc,
        "4. Analyze": t_ana,
        "5. Physics (MLD)": t_phys_mld,
        "6. Physics (TCHP)": t_phys_tchp,
        "7. Physics (Acoustic)": t_phys_acou,
        "8. Plot: Profile": t_plot_prof,
        "9. Plot: T-S": t_plot_ts,
        "10. Plot: Map": t_plot_map,
        "11. Plot: Thermocline": t_plot_mld,
        "12. Plot: TCHP": t_plot_tchp,
        "13. Plot: Acoustic": t_plot_acou,
        "14. Card Build": t_card,
        "15. SQLite Save": t_save,
        "16. SQLite List": t_list,
        "17. Card Restore": t_restore,
        "18. Total Pipeline.run (mocked fetch)": t_pipeline,
    }

    for k, v in results.items():
        print(f"{k:40} : {v*1000:8.2f} ms ({v:6.4f} s)")

    return results


def main():
    df_fixture, df_cache = load_datasets()

    print("Running memory tracking and multi-pass timing...")
    tracemalloc.start()

    times_cache = []
    for run_idx in range(3):
        print(f"\n--- Run {run_idx + 1}/3 on Largest Cache ---")
        t_res = run_benchmarks(df_cache, f"Cache Parquet (Pass {run_idx+1})")
        times_cache.append(t_res)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\nPeak Memory Tracked: {peak / (1024*1024):.2f} MB")

    # Median summary table
    keys = list(times_cache[0].keys())
    print("\n================ MEDIAN SUMMARY (3 RUNS ON 59,163 ROWS) ================")
    for k in keys:
        vals = sorted([tc[k] for tc in times_cache])
        med = vals[1]
        print(f"{k:40} : {med*1000:8.2f} ms ({med:6.4f} s)")

    # Run cProfile on the slowest stage / entire pipeline run on large cache
    print("\n--- Running cProfile on complete pipeline.run over large dataset ---")
    profiler = cProfile.Profile()
    spec = parse_detailed("temperature in the Arabian Sea between 2022-01-01 and 2022-01-10").spec
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_cache,
        is_cached=True,
        cache_key=spec.fetch_key(),
        profile_count_verified=True,
        profile_count=df_cache["PLATFORM_NUMBER"].nunique(),
    )
    with patch("siqva.pipeline.fetch", return_value=fetch_res):
        profiler.enable()
        run(question="temperature in the Arabian Sea between 2022-01-01 and 2022-01-10")
        profiler.disable()

    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(15)
    print(s.getvalue())


if __name__ == "__main__":
    main()
