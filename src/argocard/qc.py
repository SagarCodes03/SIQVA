"""Quality Control (QC) documentation, auditing, and reporting for Argo data."""

from __future__ import annotations

from typing import Any, Optional
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .spec import DataMode, Variable


# ==============================================================================
# ARGOPY USER-MODE FILTERING DOCUMENTATION (FROM INSTALLED ARGOPY 1.4.0 DOCS & SOURCE)
# ==============================================================================
#
# Argopy DataFetcher defines its post-processing workflow in
# `argopy.fetchers.ArgoDataFetcher.define_postprocessor()` and xarray accessors:
#
# 1. RESEARCH MODE (`mode="research"`):
#    Source: `argopy.xarray.ArgoAccessor.filter_researchmode()`
#    - For physical dataset ('phy' - core/deep missions):
#      * Restricts data to delayed mode only: `DATA_MODE == 'D'`. Real-time data is excluded.
#      * Merges adjusted fields into primary parameter columns: `this.argo.datamode.merge(params=core_params)`.
#        (e.g., replaces TEMP with TEMP_ADJUSTED, PSAL with PSAL_ADJUSTED, PRES with PRES_ADJUSTED).
#      * Enforces QC = 1 strictly:
#        - `POSITION_QC == 1`
#        - `TIME_QC == 1`
#        - Core variable QCs: `TEMP_QC == 1`, `PSAL_QC == 1`, `PRES_QC == 1`.
#        (QC = 2 "Probably good" is dropped; only QC = 1 "Good" is retained).
#      * Restricts pressure errors: `PRES_ERROR < 20 dbar` (drops points with error >= 20 dbar).
#
# 2. STANDARD MODE (`mode="standard"`):
#    Source: `argopy.fetchers.ArgoDataFetcher.define_postprocessor()`
#    - Applies `transform_data_mode()`: merges adjusted values when available, but includes
#      both real-time ('R'), adjusted real-time ('A'), and delayed-mode ('D') profiles.
#    - Applies `filter_qc(QC_list=[1, 2])`:
#      * Retains measurements with QC = 1 ("Good") and QC = 2 ("Probably Good").
#      * Drops measurements with QC = 3 ("Probably Bad"), QC = 4 ("Bad"), QC = 0 ("No QC").
#
# 3. EXPERT MODE (`mode="expert"`):
#    Source: `argopy.fetchers.ArgoDataFetcher.define_postprocessor()`
#    - Workflow is `lambda x: x` (identity function).
#    - No data mode filtering is performed (all of 'R', 'A', 'D' remain).
#    - No QC filtering is performed (all QC flags 0, 1, 2, 3, 4, 5, 8, 9 remain intact).
#    - Raw unadjusted variables and separate *_ADJUSTED columns are returned without merging.
#
# ==============================================================================


def get_qc_filter_description(mode: DataMode) -> str:
    """Return explicit deterministic description of QC filter in effect for a given mode."""
    if mode == DataMode.RESEARCH:
        return "Strict QC=1 only (good data); flags >1 and real-time records excluded."
    elif mode == DataMode.STANDARD:
        return "QC=1 (good) and QC=2 (probably good) retained; flags 0, 3, 4 excluded."
    elif mode == DataMode.EXPERT:
        return "No QC filtering applied; all QC flags (0-9) retained as measured."
    return "Custom QC filter"


def get_mode_description(mode: DataMode) -> str:
    """Return explicit deterministic description of mode filtering."""
    if mode == DataMode.RESEARCH:
        return "delayed-mode only, QC=1 only, adjusted values merged"
    elif mode == DataMode.STANDARD:
        return "real-time and delayed-mode, QC 1 and 2, adjusted values merged"
    elif mode == DataMode.EXPERT:
        return "raw unadjusted data, all QC flags 0–9 included without filtering"
    return str(mode.value)


class VariableQCStats(BaseModel):
    """Quality control audit statistics for a single physical variable."""

    model_config = ConfigDict(frozen=True)

    variable: str
    qc_column: Optional[str] = None
    total_measured: int
    good_count: int  # QC == 1
    probably_good_count: int  # QC == 2
    non_good_count: int  # QC != 1
    flag_counts: dict[int, int] = Field(default_factory=dict)
    flag_percentages: dict[int, float] = Field(default_factory=dict)
    profiles_with_non_good: int = 0


class QCReport(BaseModel):
    """Comprehensive post-fetch quality control audit report.

    Reports on QC flag distributions across variables and profiles without silently dropping rows.
    """

    model_config = ConfigDict(frozen=True)

    mode: DataMode
    total_rows: int
    total_profiles: int
    variable_stats: dict[str, VariableQCStats] = Field(default_factory=dict)
    position_qc_non_good_rows: int = 0
    time_qc_non_good_rows: int = 0
    summary_message: str


def audit_qc(
    df: pd.DataFrame,
    variables: list[Variable],
    mode: DataMode,
) -> QCReport:
    """Perform post-fetch QC audit on fetched Argo DataFrame without dropping any rows.

    Inspects each requested variable's QC flags (e.g. TEMP_QC, PSAL_QC, PRES_QC),
    tallies non-good counts (QC != 1), flag frequency breakdown, and impacted profiles.

    Args:
        df: Fetched DataFrame from argopy.
        variables: List of requested physical variables from QuerySpec.
        mode: Argo data mode from QuerySpec.

    Returns:
        QCReport documenting QC audit without row loss.
    """
    total_rows = len(df)
    if total_rows == 0:
        return QCReport(
            mode=mode,
            total_rows=0,
            total_profiles=0,
            variable_stats={},
            summary_message="Empty dataset (0 rows).",
        )

    # Count profiles by PLATFORM_NUMBER and CYCLE_NUMBER if available
    col_names = [str(c) for c in df.columns]
    has_platform = "PLATFORM_NUMBER" in col_names
    has_cycle = "CYCLE_NUMBER" in col_names

    if has_platform and has_cycle:
        total_profiles = df.groupby(["PLATFORM_NUMBER", "CYCLE_NUMBER"]).ngroups
    elif has_cycle:
        total_profiles = int(df["CYCLE_NUMBER"].nunique())
    else:
        total_profiles = 1

    var_stats: dict[str, VariableQCStats] = {}
    summary_lines: list[str] = [
        f"QC audit for mode '{mode.value}': {total_rows:,} rows across {total_profiles:,} profiles."
    ]

    for var in variables:
        qc_col_target = f"{var.value}_QC"
        val_col_target = var.value

        # Locate QC column case-insensitively
        matching_qc_cols = [c for c in df.columns if str(c).upper() == qc_col_target]
        matching_val_cols = [c for c in df.columns if str(c).upper() == val_col_target]

        if not matching_qc_cols:
            val_col = matching_val_cols[0] if matching_val_cols else None
            measured = int(df[val_col].notna().sum()) if val_col else total_rows
            var_stats[var.value] = VariableQCStats(
                variable=var.value,
                qc_column=None,
                total_measured=measured,
                good_count=0,
                probably_good_count=0,
                non_good_count=0,
                flag_counts={},
                flag_percentages={},
                profiles_with_non_good=0,
            )
            continue

        actual_qc_col = matching_qc_cols[0]
        qc_series = df[actual_qc_col].dropna()
        qc_numeric = pd.to_numeric(qc_series, errors="coerce").dropna().astype(int)

        flag_counts = {int(k): int(v) for k, v in qc_numeric.value_counts().to_dict().items()}
        total_measured = len(qc_numeric)
        flag_percentages = {
            flag: round(count / total_measured * 100.0, 2)
            for flag, count in flag_counts.items()
        }

        good_cnt = flag_counts.get(1, 0)
        prob_good_cnt = flag_counts.get(2, 0)
        non_good_cnt = sum(c for f, c in flag_counts.items() if f != 1)

        # Count profiles with non-good measurements
        profiles_with_non_good = 0
        if has_cycle:
            non_good_flags = [f for f in flag_counts.keys() if f != 1]
            non_good_mask = df[actual_qc_col].isin(non_good_flags)
            if has_platform:
                profiles_with_non_good = df[non_good_mask].groupby(["PLATFORM_NUMBER", "CYCLE_NUMBER"]).ngroups
            else:
                profiles_with_non_good = int(df[non_good_mask]["CYCLE_NUMBER"].nunique())

        var_stats[var.value] = VariableQCStats(
            variable=var.value,
            qc_column=str(actual_qc_col),
            total_measured=total_measured,
            good_count=good_cnt,
            probably_good_count=prob_good_cnt,
            non_good_count=non_good_cnt,
            flag_counts=flag_counts,
            flag_percentages=flag_percentages,
            profiles_with_non_good=profiles_with_non_good,
        )

        summary_lines.append(
            f"{var.value}: {good_cnt:,} good (QC=1), {prob_good_cnt:,} probably good (QC=2), "
            f"{non_good_cnt:,} non-good (QC!=1) across {profiles_with_non_good} profiles."
        )

    # Position and Time QC audits
    pos_non_good = 0
    pos_cols = [c for c in df.columns if str(c).upper() == "POSITION_QC"]
    if pos_cols:
        pos_qc = pd.to_numeric(df[pos_cols[0]], errors="coerce").dropna().astype(int)
        pos_non_good = int((pos_qc != 1).sum())

    time_non_good = 0
    time_cols = [c for c in df.columns if str(c).upper() == "TIME_QC"]
    if time_cols:
        t_qc = pd.to_numeric(df[time_cols[0]], errors="coerce").dropna().astype(int)
        time_non_good = int((t_qc != 1).sum())

    return QCReport(
        mode=mode,
        total_rows=total_rows,
        total_profiles=total_profiles,
        variable_stats=var_stats,
        position_qc_non_good_rows=pos_non_good,
        time_qc_non_good_rows=time_non_good,
        summary_message=" ".join(summary_lines),
    )

