"""Tests for deterministic data operations and statistical templates (Q5)."""

import ast
from pathlib import Path
import pandas as pd
import pytest

from siqva.operations import (
    OperationResult,
    OperationSpec,
    OperationType,
    SpatialGrouping,
    TemporalGrouping,
    answer_text,
    execute,
)
from siqva.spec import DepthRange, Variable


@pytest.fixture
def sample_argo_df() -> pd.DataFrame:
    """Hand-computed Argo dataset across 2 profiles, 2 months, and varying depths."""
    return pd.DataFrame({
        "PLATFORM_NUMBER": [100, 100, 200, 200],
        "CYCLE_NUMBER": [1, 1, 2, 2],
        "PRES": [50.0, 150.0, 50.0, 250.0],
        "TEMP": [20.0, 18.0, 26.0, 16.0],
        "PSAL": [35.0, 35.5, 36.0, 36.5],
        "TIME": pd.to_datetime(["2023-01-10", "2023-01-10", "2023-02-15", "2023-02-15"]),
    })


def test_no_llm_imports_in_operations_module():
    """Verify strictly zero LLM imports in src/siqva/operations.py."""
    module_path = Path(__file__).resolve().parent.parent / "src" / "siqva" / "operations.py"
    with open(module_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    imported_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.append(node.module)

    for name in imported_names:
        assert "ollama" not in name.lower()
        assert "llm" not in name.lower()


def test_hand_computed_scalar_operations(sample_argo_df: pd.DataFrame):
    # Mean TEMP: (20 + 18 + 26 + 16) / 4 = 20.0
    spec_mean = OperationSpec(variable=Variable.TEMP, op=OperationType.MEAN)
    res_mean = execute(spec_mean, sample_argo_df)
    assert res_mean.value == 20.0
    assert res_mean.profile_count == 2
    assert res_mean.row_count == 4
    assert res_mean.unit == "°C"
    assert "The mean temperature is 20.00 °C across 2 profiles (4 observations)." in res_mean.summary

    # Median TEMP: sorted [16, 18, 20, 26] -> median = 19.0
    spec_median = OperationSpec(variable=Variable.TEMP, op=OperationType.MEDIAN)
    res_median = execute(spec_median, sample_argo_df)
    assert res_median.value == 19.0

    # Min and Max
    spec_min = OperationSpec(variable=Variable.TEMP, op=OperationType.MIN)
    res_min = execute(spec_min, sample_argo_df)
    assert res_min.value == 16.0

    spec_max = OperationSpec(variable=Variable.TEMP, op=OperationType.MAX)
    res_max = execute(spec_max, sample_argo_df)
    assert res_max.value == 26.0

    # Count
    spec_count = OperationSpec(variable=Variable.PSAL, op=OperationType.COUNT)
    res_count = execute(spec_count, sample_argo_df)
    assert res_count.value == 4.0
    assert "There are 4 observations (2 profiles) of salinity." in res_count.summary


def test_depth_slicing_operation(sample_argo_df: pd.DataFrame):
    # Only records between 0 and 100 dbar: rows 1 and 3 (both at 50 dbar)
    # TEMP: [20.0, 26.0] -> Mean = 23.0
    # PSAL: [35.0, 36.0] -> Mean = 35.5
    spec_depth = OperationSpec(
        variable=Variable.TEMP,
        op=OperationType.MEAN,
        depth_range=DepthRange(min_depth=0.0, max_depth=100.0),
    )
    res = execute(spec_depth, sample_argo_df)
    assert res.value == 23.0
    assert res.row_count == 2
    assert res.profile_count == 2
    assert "between 0 and 100 dbar" in res.summary
    assert "23.00 °C" in res.summary


def test_monthly_grouping_operation(sample_argo_df: pd.DataFrame):
    # Month 2023-01: rows 1 and 2 -> TEMP mean: (20 + 18) / 2 = 19.0
    # Month 2023-02: rows 3 and 4 -> TEMP mean: (26 + 16) / 2 = 21.0
    spec_monthly = OperationSpec(
        variable=Variable.TEMP,
        op=OperationType.MEAN,
        temporal_grouping=TemporalGrouping.MONTH,
    )
    res = execute(spec_monthly, sample_argo_df)
    assert res.grouped_values is not None
    assert res.grouped_values["2023-01"] == 19.0
    assert res.grouped_values["2023-02"] == 21.0


def test_anomaly_calculation(sample_argo_df: pd.DataFrame):
    # Overall mean TEMP = 20.0
    # Baseline = 22.0 -> anomaly = 20.0 - 22.0 = -2.00
    spec_anom = OperationSpec(
        variable=Variable.TEMP,
        op=OperationType.ANOMALY,
        baseline_value=22.0,
    )
    res = execute(spec_anom, sample_argo_df)
    assert res.value == -2.0
    assert "-2.00 °C" in res.summary
    assert "relative to baseline (22.00 °C)" in res.summary


def test_empty_dataframe_handling():
    spec = OperationSpec(variable=Variable.TEMP, op=OperationType.MEAN)
    empty_df = pd.DataFrame()
    res = execute(spec, empty_df)
    assert res.value is None
    assert res.row_count == 0
    assert "No data available" in res.summary
