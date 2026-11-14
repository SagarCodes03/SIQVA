"""Unit tests for siqva.qc module and QC auditing functionality."""

from pathlib import Path
import pandas as pd
import pytest

from siqva.qc import QCReport, VariableQCStats, audit_qc, get_qc_filter_description
from siqva.spec import DataMode, Variable

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_argo_standard.parquet"


def test_qc_audit_with_recorded_fixture():
    df = pd.read_parquet(FIXTURE_PATH)
    report = audit_qc(df, [Variable.TEMP, Variable.PSAL, Variable.PRES], DataMode.RESEARCH)

    assert isinstance(report, QCReport)
    assert report.total_rows == 188
    assert report.total_profiles == 2
    assert report.mode == DataMode.RESEARCH

    # Check TEMP stats
    assert "TEMP" in report.variable_stats
    temp_stats = report.variable_stats["TEMP"]
    assert temp_stats.good_count == 188
    assert temp_stats.non_good_count == 0
    assert temp_stats.flag_counts == {1: 188}
    assert temp_stats.profiles_with_non_good == 0

    # Ensure no rows were dropped
    assert len(df) == 188


def test_qc_audit_with_synthetic_non_good_flags():
    # Construct a synthetic DataFrame with mixed QC flags across multiple profiles
    data = {
        "PLATFORM_NUMBER": [1001, 1001, 1001, 1002, 1002],
        "CYCLE_NUMBER": [1, 1, 2, 1, 2],
        "TEMP": [25.0, 24.5, 23.0, 22.0, 21.0],
        "TEMP_QC": [1, 1, 3, 2, 4],  # 2 good (1), 1 probably good (2), 1 probably bad (3), 1 bad (4)
        "PSAL": [35.0, 35.1, 35.2, 35.3, 35.4],
        "PSAL_QC": [1, 1, 1, 1, 1],  # all good
        "PRES": [10.0, 20.0, 10.0, 10.0, 20.0],
        "PRES_QC": [1, 1, 1, 1, 1],
        "POSITION_QC": [1, 1, 1, 2, 1],
        "TIME_QC": [1, 1, 1, 1, 1],
    }
    df = pd.DataFrame(data)

    report = audit_qc(df, [Variable.TEMP, Variable.PSAL], DataMode.EXPERT)

    assert report.total_rows == 5
    assert report.total_profiles == 4  # (1001,1), (1001,2), (1002,1), (1002,2)

    temp_stats = report.variable_stats["TEMP"]
    assert temp_stats.total_measured == 5
    assert temp_stats.good_count == 2
    assert temp_stats.probably_good_count == 1
    assert temp_stats.non_good_count == 3  # flags 2, 3, 4 are non-good (QC != 1)
    assert temp_stats.flag_counts[1] == 2
    assert temp_stats.flag_counts[2] == 1
    assert temp_stats.flag_counts[3] == 1
    assert temp_stats.flag_counts[4] == 1
    # Profiles with non-good TEMP: (1001, 2), (1002, 1), (1002, 2) = 3 profiles
    assert temp_stats.profiles_with_non_good == 3

    # Position QC has 1 row with QC != 1
    assert report.position_qc_non_good_rows == 1
    assert report.time_qc_non_good_rows == 0

    # Confirm rows were not dropped
    assert len(df) == 5


def test_qc_audit_empty_dataframe():
    df = pd.DataFrame()
    report = audit_qc(df, [Variable.TEMP], DataMode.STANDARD)
    assert report.total_rows == 0
    assert report.total_profiles == 0
    assert report.variable_stats == {}
    assert "Empty dataset" in report.summary_message


def test_qc_audit_missing_qc_column():
    # DataFrame without explicit QC columns
    df = pd.DataFrame({"TEMP": [20.0, 21.0, 22.0], "CYCLE_NUMBER": [1, 1, 2]})
    report = audit_qc(df, [Variable.TEMP], DataMode.STANDARD)
    assert report.total_rows == 3
    assert report.variable_stats["TEMP"].qc_column is None
    assert report.variable_stats["TEMP"].total_measured == 3
    assert report.variable_stats["TEMP"].non_good_count == 0


def test_qc_filter_descriptions():
    """Verify explicit deterministic QC filter descriptions for all data modes."""
    assert (
        get_qc_filter_description(DataMode.RESEARCH)
        == "Strict QC=1 only (good data); all other flags and real-time records excluded."
    )
    assert (
        get_qc_filter_description(DataMode.STANDARD)
        == "only QC flags 1 and 2 are retained; all other flags are excluded"
    )
    assert (
        get_qc_filter_description(DataMode.EXPERT)
        == "No QC filtering applied; all QC flags (0-9) retained as measured."
    )


def test_real_filter_code_path_flag_survival():
    """Prove flag survival across research, standard, and expert modes using real argopy filters.

    Constructs a synthetic dataset with QC flags 0 through 9 and feeds it through
    the real filter code paths (filter_researchmode, filter_qc(QC_list=[1, 2]), and
    identity for expert) to prove exactly which flags survive in each mode.
    """
    import numpy as np
    import xarray as xr
    import argopy

    # Create synthetic dataset with points having TEMP_QC from 0 to 9
    flags = list(range(10))  # 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
    n_pts = len(flags)

    ds = xr.Dataset(
        {
            "TEMP": ("N_POINTS", np.linspace(20.0, 10.0, n_pts)),
            "TEMP_ADJUSTED": ("N_POINTS", np.linspace(20.0, 10.0, n_pts)),
            "TEMP_QC": ("N_POINTS", flags),
            "PRES": ("N_POINTS", np.linspace(10.0, 100.0, n_pts)),
            "PRES_ADJUSTED": ("N_POINTS", np.linspace(10.0, 100.0, n_pts)),
            "PRES_QC": ("N_POINTS", np.ones(n_pts, dtype=int)),
            "PRES_ERROR": ("N_POINTS", np.ones(n_pts, dtype=float) * 5.0),  # < 20 dbar
            "POSITION_QC": ("N_POINTS", np.ones(n_pts, dtype=int)),
            "TIME_QC": ("N_POINTS", np.ones(n_pts, dtype=int)),
            "LATITUDE": ("N_POINTS", np.zeros(n_pts)),
            "LONGITUDE": ("N_POINTS", np.zeros(n_pts)),
            "TIME": ("N_POINTS", pd.date_range("2020-01-01", periods=n_pts)),
            "DIRECTION": ("N_POINTS", ["A"] * n_pts),
            "DATA_MODE": ("N_POINTS", ["D"] * n_pts),
            "PLATFORM_NUMBER": ("N_POINTS", [1000] * n_pts),
            "CYCLE_NUMBER": ("N_POINTS", [1] * n_pts),
        }
    )
    ds["N_POINTS"] = np.arange(n_pts)
    ds.argo._type = "point"

    # --- STANDARD MODE FILTER PATH ---
    # Real filter applied by argopy in standard mode: filter_qc(QC_list=[1, 2])
    std_filtered_ds = ds.argo.filter_qc(QC_list=[1, 2])
    std_df = std_filtered_ds.to_dataframe()
    surviving_std_flags = sorted(int(f) for f in std_df["TEMP_QC"].unique())

    # Only QC flags 1 and 2 are retained; flags 0, 3, 4, 5, 6, 7, 8, 9 are ALL excluded
    assert surviving_std_flags == [1, 2]
    assert len(std_df) == 2
    for excluded_flag in [0, 3, 4, 5, 6, 7, 8, 9]:
        assert excluded_flag not in surviving_std_flags

    # --- RESEARCH MODE FILTER PATH ---
    # Real filter applied by argopy in research mode: filter_researchmode()
    res_filtered_ds = ds.argo.filter_researchmode()
    res_df = res_filtered_ds.to_dataframe()
    surviving_res_flags = sorted(int(f) for f in res_df["TEMP_QC"].unique())

    # Only QC flag 1 is retained; all other flags are excluded
    assert surviving_res_flags == [1]
    assert len(res_df) == 1
    for excluded_flag in [0, 2, 3, 4, 5, 6, 7, 8, 9]:
        assert excluded_flag not in surviving_res_flags

    # --- EXPERT MODE FILTER PATH ---
    # Real filter applied in expert mode: identity (lambda x: x)
    exp_df = ds.to_dataframe()
    surviving_exp_flags = sorted(int(f) for f in exp_df["TEMP_QC"].unique())

    # All QC flags 0 through 9 are retained as measured
    assert surviving_exp_flags == list(range(10))
    assert len(exp_df) == 10
