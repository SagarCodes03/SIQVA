"""Deterministic oceanographic data analysis and structured reporting for ArgoCard."""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .fetcher import FetchResult, count_unique_profiles
from .qc import get_mode_description, get_qc_filter_description
from .spec import DataMode, DepthRange, QuerySpec, Variable

STANDARD_DEPTH_BINS = [
    (0.0, 100.0, "0–100 dbar"),
    (100.0, 500.0, "100–500 dbar"),
    (500.0, 2000.0, "500–2000 dbar"),
]


class DepthBinStats(BaseModel):
    """Statistical breakdown within a specific vertical depth layer."""

    model_config = ConfigDict(frozen=True)

    bin_label: str
    min_depth: float
    max_depth: float
    min_value: Optional[float] = None
    observation_mean: Optional[float] = None
    max_value: Optional[float] = None
    observation_count: int = 0


class VariableStats(BaseModel):
    """Statistical summary for a single physical variable."""

    model_config = ConfigDict(frozen=True)

    variable: str
    min_value: Optional[float] = None
    mean_value: Optional[float] = None
    max_value: Optional[float] = None
    observation_count: int = 0
    missing_count: int = 0
    depth_bins: list[DepthBinStats] = Field(default_factory=list)


class ProfileDepthStats(BaseModel):
    """Per-profile vertical sampling depth coverage."""

    model_config = ConfigDict(frozen=True)

    platform_number: Any
    cycle_number: Any
    shallowest_depth: float
    deepest_depth: float
    reached_requested_depth: bool


class AnalysisResult(BaseModel):
    """Deterministic summary statistics and metadata for fetched Argo observations."""

    model_config = ConfigDict(frozen=True)

    profile_count: int
    observation_count: int
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    variable_stats: dict[str, VariableStats] = Field(default_factory=dict)
    depth_coverage: list[ProfileDepthStats] = Field(default_factory=list)
    shallowest_level_overall: Optional[float] = None
    deepest_level_overall: Optional[float] = None
    fraction_reaching_requested_depth: float = 0.0
    missing_data_notes: list[str] = Field(default_factory=list)
    mode: DataMode
    qc_filter_description: str
    effective_depth_range: DepthRange
    is_default_depth: bool
    is_cached: bool
    profile_count_verified: bool
    summary: str


def summary_text(analysis: AnalysisResult) -> str:
    """Generate deterministic summary text from fixed templates without an LLM.

    Always includes:
      - mode
      - QC filter in effect (imported from qc.py)
      - effective depth range (flag when 0-500 dbar default)
      - profiles used
      - whether data was cached
      - 'profile count unverified' when profile_count_verified is False
      - observation mean explicitly labeled as 'observation mean (not depth-weighted)'
      - per-depth-bin statistics for bins within the effective depth range
    """
    lines = [
        f"**Mode**: `{analysis.mode.value}` ({get_mode_description(analysis.mode)})",
        f"**QC Filter in effect**: {analysis.qc_filter_description}",
    ]

    if analysis.is_default_depth:
        lines.append(
            f"**Effective depth range**: {analysis.effective_depth_range.min_depth:.1f} – "
            f"{analysis.effective_depth_range.max_depth:.1f} dbar *(default 0–500 dbar applied because none was specified)*"
        )
    else:
        lines.append(
            f"**Effective depth range**: {analysis.effective_depth_range.min_depth:.1f} – "
            f"{analysis.effective_depth_range.max_depth:.1f} dbar"
        )

    lines.append(f"**Profiles used**: {analysis.profile_count}")
    lines.append(f"**Observations**: {analysis.observation_count}")

    if not analysis.profile_count_verified:
        lines.append("⚠️ **Notice**: profile count unverified (query extends beyond snapshot bounds or coverage was partial/absent).")

    if analysis.is_cached:
        lines.append("**Data status**: Cached from local store.")
    else:
        lines.append("**Data status**: Fetched remotely from ERDDAP server.")

    if analysis.date_start and analysis.date_end:
        lines.append(f"**Temporal span**: {analysis.date_start} to {analysis.date_end}")

    if analysis.fraction_reaching_requested_depth > 0 or analysis.profile_count > 0:
        if analysis.shallowest_level_overall is not None and analysis.deepest_level_overall is not None:
            lines.append(
                f"**Depth coverage**: {analysis.fraction_reaching_requested_depth * 100:.1f}% of profiles "
                f"reached requested target depth ({analysis.effective_depth_range.max_depth:.0f} dbar). "
                f"Overall sampled levels: {analysis.shallowest_level_overall:.1f} – {analysis.deepest_level_overall:.1f} dbar."
            )

    var_summaries = []
    for var_name, v_stat in analysis.variable_stats.items():
        if v_stat.observation_count > 0 and v_stat.min_value is not None and v_stat.mean_value is not None:
            entry = [
                f"- **{var_name}**: range = {v_stat.min_value:.2f} – {v_stat.max_value:.2f}, "
                f"observation mean (not depth-weighted) = {v_stat.mean_value:.2f} "
                f"({v_stat.observation_count} points, {v_stat.missing_count} missing)"
            ]
            if v_stat.depth_bins:
                for b in v_stat.depth_bins:
                    if b.observation_count > 0 and b.observation_mean is not None and b.min_value is not None:
                        entry.append(
                            f"  * *{b.bin_label}*: range = {b.min_value:.2f} – {b.max_value:.2f}, "
                            f"observation mean (not depth-weighted) = {b.observation_mean:.2f} ({b.observation_count} obs)"
                        )
            var_summaries.append("\n".join(entry))

    if var_summaries:
        lines.append("**Physical Variables**:\n" + "\n".join(var_summaries))

    if analysis.missing_data_notes:
        lines.append("**Missing data notes**:\n" + "\n".join(f"- {note}" for note in analysis.missing_data_notes))

    return "\n\n".join(lines)


def analyze(
    df: Optional[pd.DataFrame],
    spec: QuerySpec,
    fetch_result: FetchResult,
) -> AnalysisResult:
    """Compute deterministic oceanographic summary statistics from fetched Argo data.

    Args:
        df: Fetched DataFrame of Argo observations (or None / empty).
        spec: Validated QuerySpec.
        fetch_result: FetchResult from fetcher module.

    Returns:
        AnalysisResult containing statistics, depth coverage, and formatted summary.
    """
    effective_depth = fetch_result.effective_depth_range
    is_default_depth = (spec.depth_range is None)
    qc_desc = get_qc_filter_description(spec.mode)

    if df is None or len(df) == 0:
        base_res = AnalysisResult(
            profile_count=0,
            observation_count=0,
            date_start=None,
            date_end=None,
            variable_stats={},
            depth_coverage=[],
            shallowest_level_overall=None,
            deepest_level_overall=None,
            fraction_reaching_requested_depth=0.0,
            missing_data_notes=["No observation rows found in dataset."],
            mode=spec.mode,
            qc_filter_description=qc_desc,
            effective_depth_range=effective_depth,
            is_default_depth=is_default_depth,
            is_cached=fetch_result.is_cached,
            profile_count_verified=fetch_result.profile_count_verified,
            summary="",
        )
        return base_res.model_copy(update={"summary": summary_text(base_res)})

    observation_count = len(df)
    profile_count = count_unique_profiles(df)

    # Date span
    date_start = None
    date_end = None
    time_col = None
    for cand in ["TIME", "date", "time"]:
        if cand in df.columns:
            time_col = cand
            break
    if time_col is not None:
        valid_times = pd.to_datetime(df[time_col], errors="coerce").dropna()
        if not valid_times.empty:
            date_start = str(valid_times.min().strftime("%Y-%m-%d %H:%M:%S"))
            date_end = str(valid_times.max().strftime("%Y-%m-%d %H:%M:%S"))

    # Determine depth bins within the effective depth range
    applicable_bins = []
    for b_min, b_max, label in STANDARD_DEPTH_BINS:
        if b_min < effective_depth.max_depth and b_max > effective_depth.min_depth:
            # Overlaps effective depth range
            actual_min = max(b_min, effective_depth.min_depth)
            actual_max = min(b_max, effective_depth.max_depth)
            bin_label = f"{actual_min:.0f}–{actual_max:.0f} dbar" if (actual_min != b_min or actual_max != b_max) else label
            applicable_bins.append((actual_min, actual_max, bin_label))

    # Per-variable statistics
    variable_stats: dict[str, VariableStats] = {}
    missing_notes: list[str] = []

    vars_to_check = set(v.value for v in spec.variables)
    for std_var in ["TEMP", "PSAL", "PRES"]:
        if std_var in df.columns:
            vars_to_check.add(std_var)

    pres_col = "PRES" if "PRES" in df.columns else None

    for var in sorted(vars_to_check):
        if var in df.columns:
            series = pd.to_numeric(df[var], errors="coerce")
            missing_cnt = int(series.isna().sum())
            valid_series = series.dropna()
            obs_cnt = int(len(valid_series))

            if obs_cnt > 0:
                v_min = float(valid_series.min())
                v_mean = float(valid_series.mean())
                v_max = float(valid_series.max())
            else:
                v_min, v_mean, v_max = None, None, None

            # Calculate per-depth-bin statistics if pressure column is available
            depth_bins_stats: list[DepthBinStats] = []
            if pres_col and var != pres_col and obs_cnt > 0:
                pres_series = pd.to_numeric(df[pres_col], errors="coerce")
                for b_min, b_max, b_lbl in applicable_bins:
                    in_bin_mask = (pres_series >= b_min) & (pres_series <= b_max) & series.notna()
                    bin_vals = series[in_bin_mask]
                    if len(bin_vals) > 0:
                        depth_bins_stats.append(
                            DepthBinStats(
                                bin_label=b_lbl,
                                min_depth=b_min,
                                max_depth=b_max,
                                min_value=float(bin_vals.min()),
                                observation_mean=float(bin_vals.mean()),
                                max_value=float(bin_vals.max()),
                                observation_count=len(bin_vals),
                            )
                        )

            variable_stats[var] = VariableStats(
                variable=var,
                min_value=v_min,
                mean_value=v_mean,
                max_value=v_max,
                observation_count=obs_cnt,
                missing_count=missing_cnt,
                depth_bins=depth_bins_stats,
            )

            if missing_cnt > 0:
                pct = (missing_cnt / len(df)) * 100.0
                missing_notes.append(f"{var}: {missing_cnt} missing values ({pct:.1f}%).")
        else:
            missing_notes.append(f"{var}: Requested variable column not found in returned dataset.")

    # Depth coverage per profile
    depth_coverage: list[ProfileDepthStats] = []
    has_plat = "PLATFORM_NUMBER" in df.columns
    has_cyc = "CYCLE_NUMBER" in df.columns

    shallowest_overall = None
    deepest_overall = None
    reached_target_count = 0

    if pres_col and has_plat and has_cyc:
        grouped = df.groupby(["PLATFORM_NUMBER", "CYCLE_NUMBER"])
        for (plat, cyc), group in grouped:
            pres_vals = pd.to_numeric(group[pres_col], errors="coerce").dropna()
            if not pres_vals.empty:
                shallowest = float(pres_vals.min())
                deepest = float(pres_vals.max())
                reached = deepest >= (effective_depth.max_depth - 10.0)
                if reached:
                    reached_target_count += 1

                depth_coverage.append(
                    ProfileDepthStats(
                        platform_number=plat,
                        cycle_number=cyc,
                        shallowest_depth=shallowest,
                        deepest_depth=deepest,
                        reached_requested_depth=reached,
                    )
                )

        if depth_coverage:
            shallowest_overall = float(min(d.shallowest_depth for d in depth_coverage))
            deepest_overall = float(max(d.deepest_depth for d in depth_coverage))

    fraction_reaching = (
        float(reached_target_count / len(depth_coverage)) if depth_coverage else 0.0
    )

    base_res = AnalysisResult(
        profile_count=profile_count,
        observation_count=observation_count,
        date_start=date_start,
        date_end=date_end,
        variable_stats=variable_stats,
        depth_coverage=depth_coverage,
        shallowest_level_overall=shallowest_overall,
        deepest_level_overall=deepest_overall,
        fraction_reaching_requested_depth=fraction_reaching,
        missing_data_notes=missing_notes,
        mode=spec.mode,
        qc_filter_description=qc_desc,
        effective_depth_range=effective_depth,
        is_default_depth=is_default_depth,
        is_cached=fetch_result.is_cached,
        profile_count_verified=fetch_result.profile_count_verified,
        summary="",
    )

    return base_res.model_copy(update={"summary": summary_text(base_res)})
