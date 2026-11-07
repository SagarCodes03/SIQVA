"""Tests for deterministic comparison calculations and objective reporting (Q9)."""

import ast
from pathlib import Path
import pandas as pd
import pytest

from siqva.comparison import ComparisonResult, ComparisonSpec, compare
from siqva.operations import OperationSpec, OperationType
from siqva.spec import DepthRange, Variable


def test_no_llm_imports_in_comparison_module():
    """Verify strictly zero LLM imports in src/siqva/comparison.py."""
    module_path = Path(__file__).resolve().parent.parent / "src" / "siqva" / "comparison.py"
    with open(module_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "ollama" not in alias.name.lower()
                assert "llm" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "ollama" not in node.module.lower()
                assert "llm" not in node.module.lower()


def test_compare_mean_temperature():
    df_a = pd.DataFrame({
        "PLATFORM_NUMBER": [101, 101],
        "CYCLE_NUMBER": [1, 1],
        "PRES": [20.0, 50.0],
        "TEMP": [26.0, 24.0],  # Mean = 25.0
    })
    df_b = pd.DataFrame({
        "PLATFORM_NUMBER": [202, 202],
        "CYCLE_NUMBER": [1, 2],
        "PRES": [20.0, 50.0],
        "TEMP": [23.0, 22.0],  # Mean = 22.5
    })

    spec = OperationSpec(variable=Variable.TEMP, op=OperationType.MEAN)
    res = compare(spec, spec, df_a, df_b, label_a="Arabian Sea (2022)", label_b="Arabian Sea (2021)")

    assert res.difference == 2.5
    assert res.result_a.value == 25.0
    assert res.result_b.value == 22.5
    assert "In 'Arabian Sea (2022)', the mean temperature is 25.00 °C" in res.summary
    assert "In 'Arabian Sea (2021)', it is 22.50 °C" in res.summary
    assert "difference ('Arabian Sea (2022)' minus 'Arabian Sea (2021)') is +2.50 °C" in res.summary


def test_compare_negative_difference():
    df_a = pd.DataFrame({
        "PLATFORM_NUMBER": [101],
        "CYCLE_NUMBER": [1],
        "PRES": [10.0],
        "TEMP": [20.0],
    })
    df_b = pd.DataFrame({
        "PLATFORM_NUMBER": [202],
        "CYCLE_NUMBER": [1],
        "PRES": [10.0],
        "TEMP": [24.0],
    })
    spec = OperationSpec(variable=Variable.TEMP, op=OperationType.MEAN)
    res = compare(spec, spec, df_a, df_b, label_a="2021", label_b="2022")

    assert res.difference == -4.0
    assert "-4.00 °C" in res.summary


def test_compare_with_depth_range():
    df_a = pd.DataFrame({
        "PLATFORM_NUMBER": [101, 101],
        "CYCLE_NUMBER": [1, 1],
        "PRES": [50.0, 300.0],
        "PSAL": [35.5, 36.5],
    })
    df_b = pd.DataFrame({
        "PLATFORM_NUMBER": [202, 202],
        "CYCLE_NUMBER": [1, 1],
        "PRES": [50.0, 300.0],
        "PSAL": [34.5, 35.5],
    })
    depth = DepthRange(min_depth=0.0, max_depth=100.0)
    spec = OperationSpec(variable=Variable.PSAL, op=OperationType.MEAN, depth_range=depth)
    res = compare(spec, spec, df_a, df_b, label_a="Region A", label_b="Region B")

    assert res.result_a.row_count == 1
    assert res.result_a.value == 35.5
    assert res.result_b.value == 34.5
    assert res.difference == 1.0
    assert "between 0 and 100 dbar" in res.summary


def test_compare_missing_dataset_reports_clean_failure():
    df_a = pd.DataFrame({"TEMP": [25.0]})
    df_empty = pd.DataFrame()

    spec = OperationSpec(variable=Variable.TEMP, op=OperationType.MEAN)
    res = compare(spec, spec, df_a, df_empty, label_a="2022", label_b="2023")

    assert res.difference is None
    assert "could not be completed" in res.summary


def test_no_subjective_anomaly_claims_in_summary():
    """Ensure output avoids non-scientific subjective claims like 'abnormal' or 'unusual'."""
    df_a = pd.DataFrame({"TEMP": [32.0]})
    df_b = pd.DataFrame({"TEMP": [20.0]})
    spec = OperationSpec(variable=Variable.TEMP, op=OperationType.MEAN)
    res = compare(spec, spec, df_a, df_b, label_a="A", label_b="B")

    banned_words = ["abnormal", "anomalous", "unusual", "extreme", "alarming", "unprecedented"]
    for word in banned_words:
        assert word not in res.summary.lower()
