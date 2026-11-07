"""Deterministic numerical operations and statistical templates for Argo data questions (Q5).

No LLM dependencies: all calculations and text formatting are purely deterministic.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .fetcher import count_unique_profiles
from .spec import DepthRange, Variable

VARIABLE_UNITS: dict[Variable, str] = {
    Variable.TEMP: "°C",
    Variable.PSAL: "PSU",
    Variable.PRES: "dbar",
}


class OperationType(str, Enum):
    """Statistical and numerical operation types."""

    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    STD = "std"
    COUNT = "count"
    ANOMALY = "anomaly"


class TemporalGrouping(str, Enum):
    """Temporal binning/grouping options."""

    NONE = "none"
    MONTH = "month"
    YEAR = "year"
    DAY = "day"


class SpatialGrouping(str, Enum):
    """Spatial binning/grouping options."""

    NONE = "none"
    PROFILE = "profile"


class OperationSpec(BaseModel):
    """Specification of a deterministic numerical data operation."""

    model_config = ConfigDict(frozen=True)

    variable: Variable = Variable.TEMP
    op: OperationType = OperationType.MEAN
    depth_range: Optional[DepthRange] = None
    temporal_grouping: TemporalGrouping = TemporalGrouping.NONE
    spatial_grouping: SpatialGrouping = SpatialGrouping.NONE
    baseline_value: Optional[float] = None
    label: Optional[str] = None


class OperationResult(BaseModel):
    """Result of a deterministic operation execution."""

    model_config = ConfigDict(frozen=True)

    spec: OperationSpec
    value: Optional[float] = None
    grouped_values: Optional[dict[str, float]] = None
    unit: str
    row_count: int
    profile_count: int
    summary: str


def execute(spec: OperationSpec, df: Optional[pd.DataFrame]) -> OperationResult:
    """Execute a deterministic data operation on an Argo DataFrame."""
    unit = VARIABLE_UNITS.get(spec.variable, "")

    if df is None or len(df) == 0:
        return OperationResult(
            spec=spec,
            value=None,
            grouped_values=None,
            unit=unit,
            row_count=0,
            profile_count=0,
            summary=f"No data available to calculate {spec.op.value} of {spec.variable.value}.",
        )

    # 1. Depth slice filtering
    sub_df = df.copy()
    if spec.depth_range is not None and "PRES" in sub_df.columns:
        sub_df = sub_df[
            (sub_df["PRES"] >= spec.depth_range.min_depth)
            & (sub_df["PRES"] <= spec.depth_range.max_depth)
        ]

    row_count = len(sub_df)
    profile_count = count_unique_profiles(sub_df)

    var_col = spec.variable.value
    if var_col not in sub_df.columns:
        return OperationResult(
            spec=spec,
            value=None,
            grouped_values=None,
            unit=unit,
            row_count=row_count,
            profile_count=profile_count,
            summary=f"Variable '{var_col}' not present in the dataset.",
        )

    series = pd.to_numeric(sub_df[var_col], errors="coerce").dropna()
    if len(series) == 0:
        return OperationResult(
            spec=spec,
            value=None,
            grouped_values=None,
            unit=unit,
            row_count=row_count,
            profile_count=profile_count,
            summary=f"No valid observations for variable '{var_col}' within the specified constraints.",
        )

    # 2. Grouped calculations
    grouped_res: Optional[dict[str, float]] = None

    if spec.temporal_grouping != TemporalGrouping.NONE and "TIME" in sub_df.columns:
        times = pd.to_datetime(sub_df["TIME"], errors="coerce")
        valid_mask = times.notna() & sub_df[var_col].notna()
        grouped_df = sub_df[valid_mask].copy()
        grouped_df["_TIME"] = times[valid_mask]

        if spec.temporal_grouping == TemporalGrouping.MONTH:
            grouped_df["_GRP"] = grouped_df["_TIME"].dt.strftime("%Y-%m")
        elif spec.temporal_grouping == TemporalGrouping.YEAR:
            grouped_df["_GRP"] = grouped_df["_TIME"].dt.strftime("%Y")
        elif spec.temporal_grouping == TemporalGrouping.DAY:
            grouped_df["_GRP"] = grouped_df["_TIME"].dt.strftime("%Y-%m-%d")

        grp = grouped_df.groupby("_GRP")[var_col]
        if spec.op == OperationType.MEAN:
            vals = grp.mean()
        elif spec.op == OperationType.MEDIAN:
            vals = grp.median()
        elif spec.op == OperationType.MIN:
            vals = grp.min()
        elif spec.op == OperationType.MAX:
            vals = grp.max()
        elif spec.op == OperationType.STD:
            vals = grp.std(ddof=1)
        elif spec.op == OperationType.COUNT:
            vals = grp.count()
        elif spec.op == OperationType.ANOMALY:
            base = spec.baseline_value if spec.baseline_value is not None else float(series.mean())
            vals = grp.mean() - base
        else:
            vals = grp.mean()

        grouped_res = {str(k): round(float(v), 4) if pd.notna(v) else float("nan") for k, v in vals.items()}

    # 3. Overall scalar calculation
    scalar_val: Optional[float] = None
    if spec.op == OperationType.MEAN:
        scalar_val = float(series.mean())
    elif spec.op == OperationType.MEDIAN:
        scalar_val = float(series.median())
    elif spec.op == OperationType.MIN:
        scalar_val = float(series.min())
    elif spec.op == OperationType.MAX:
        scalar_val = float(series.max())
    elif spec.op == OperationType.STD:
        scalar_val = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    elif spec.op == OperationType.COUNT:
        scalar_val = float(len(series))
    elif spec.op == OperationType.ANOMALY:
        overall_mean = float(series.mean())
        base = spec.baseline_value if spec.baseline_value is not None else 0.0
        scalar_val = overall_mean - base

    if scalar_val is not None and not np.isnan(scalar_val):
        scalar_val = round(scalar_val, 4)

    # 4. Generate deterministic summary
    res = OperationResult(
        spec=spec,
        value=scalar_val,
        grouped_values=grouped_res,
        unit=unit,
        row_count=row_count,
        profile_count=profile_count,
        summary="",
    )
    summary_text = answer_text(res)
    return res.model_copy(update={"summary": summary_text})


def answer_text(result: OperationResult) -> str:
    """Format a deterministic, template-based answer sentence from an OperationResult."""
    spec = result.spec
    var_name = spec.variable.value
    var_label = "temperature" if spec.variable == Variable.TEMP else ("salinity" if spec.variable == Variable.PSAL else "pressure")
    op_name = spec.op.value

    depth_phrase = ""
    if spec.depth_range is not None:
        depth_phrase = f" between {spec.depth_range.min_depth:.0f} and {spec.depth_range.max_depth:.0f} dbar"

    if result.value is None:
        return f"Could not determine {op_name} of {var_label}{depth_phrase}."

    unit_str = f" {result.unit}" if result.unit else ""
    prof_str = f"{result.profile_count:,} profile{'s' if result.profile_count != 1 else ''}"
    obs_str = f"{result.row_count:,} observation{'s' if result.row_count != 1 else ''}"

    if spec.op == OperationType.COUNT:
        return f"There are {int(result.value):,} observations ({prof_str}) of {var_label}{depth_phrase}."

    if spec.op == OperationType.ANOMALY:
        sign = "+" if result.value > 0 else ""
        base_str = f" relative to baseline ({spec.baseline_value:.2f}{unit_str})" if spec.baseline_value is not None else ""
        return (
            f"The {var_label} anomaly{depth_phrase}{base_str} is {sign}{result.value:.2f}{unit_str} "
            f"across {prof_str} ({obs_str})."
        )

    return (
        f"The {op_name} {var_label}{depth_phrase} is {result.value:.2f}{unit_str} "
        f"across {prof_str} ({obs_str})."
    )
