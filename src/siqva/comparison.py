"""Deterministic comparison calculations across regions or time periods (Q9).

No LLM dependencies: all comparisons and reporting are purely deterministic.
Strictly avoids subjective labels like 'anomalous', 'abnormal', or 'unusual'.
"""

from __future__ import annotations

from typing import Any, Optional
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .operations import (
    VARIABLE_UNITS,
    OperationResult,
    OperationSpec,
    OperationType,
    execute,
)
from .spec import DepthRange, Variable


class ComparisonSpec(BaseModel):
    """Specification for comparing two datasets across regions or time periods."""

    model_config = ConfigDict(frozen=True)

    label_a: str = "Dataset A"
    label_b: str = "Dataset B"
    variable: Variable = Variable.TEMP
    op: OperationType = OperationType.MEAN
    depth_range: Optional[DepthRange] = None


class ComparisonResult(BaseModel):
    """Result of comparing two datasets."""

    model_config = ConfigDict(frozen=True)

    spec: ComparisonSpec
    result_a: OperationResult
    result_b: OperationResult
    difference: Optional[float] = None
    unit: str
    summary: str


def compare(
    spec_a: OperationSpec,
    spec_b: OperationSpec,
    df_a: Optional[pd.DataFrame],
    df_b: Optional[pd.DataFrame],
    label_a: str = "Dataset A",
    label_b: str = "Dataset B",
) -> ComparisonResult:
    """Execute dual deterministic operations and compare results without subjective framing."""
    res_a = execute(spec_a, df_a)
    res_b = execute(spec_b, df_b)

    unit = VARIABLE_UNITS.get(spec_a.variable, "")
    comp_spec = ComparisonSpec(
        label_a=label_a,
        label_b=label_b,
        variable=spec_a.variable,
        op=spec_a.op,
        depth_range=spec_a.depth_range,
    )

    var_label = "temperature" if spec_a.variable == Variable.TEMP else ("salinity" if spec_a.variable == Variable.PSAL else "pressure")
    op_name = spec_a.op.value

    depth_phrase = ""
    if spec_a.depth_range is not None:
        depth_phrase = f" between {spec_a.depth_range.min_depth:.0f} and {spec_a.depth_range.max_depth:.0f} dbar"

    unit_str = f" {unit}" if unit else ""

    if res_a.value is None or res_b.value is None:
        summary = (
            f"Comparison of {op_name} {var_label}{depth_phrase} between '{label_a}' and '{label_b}' "
            "could not be completed due to missing observations in one or both datasets."
        )
        return ComparisonResult(
            spec=comp_spec,
            result_a=res_a,
            result_b=res_b,
            difference=None,
            unit=unit,
            summary=summary,
        )

    diff = round(res_a.value - res_b.value, 4)
    sign = "+" if diff > 0 else ""

    summary = (
        f"In '{label_a}', the {op_name} {var_label}{depth_phrase} is {res_a.value:.2f}{unit_str} "
        f"across {res_a.profile_count:,} profile{'s' if res_a.profile_count != 1 else ''} ({res_a.row_count:,} obs). "
        f"In '{label_b}', it is {res_b.value:.2f}{unit_str} "
        f"across {res_b.profile_count:,} profile{'s' if res_b.profile_count != 1 else ''} ({res_b.row_count:,} obs). "
        f"The difference ('{label_a}' minus '{label_b}') is {sign}{diff:.2f}{unit_str}."
    )

    return ComparisonResult(
        spec=comp_spec,
        result_a=res_a,
        result_b=res_b,
        difference=diff,
        unit=unit,
        summary=summary,
    )
