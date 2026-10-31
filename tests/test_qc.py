"""Unit tests for siqva.qc module and QC auditing functionality."""

from pathlib import Path
import pandas as pd
import pytest

from siqva.qc import QCReport, VariableQCStats, audit_qc
from siqva.spec import DataMode, Variable

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


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
