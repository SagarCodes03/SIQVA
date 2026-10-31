"""Unit tests for siqva.analyzer module (deterministic oceanographic stats and summaries)."""

from datetime import date
from pathlib import Path
import pandas as pd
import pytest

from siqva.analyzer import AnalysisResult, analyze, summary_text
from siqva.fetcher import FetchResult, FetchStatus
from siqva.qc import get_mode_description, get_qc_filter_description
from siqva.spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


@pytest.fixture
def sample_spec() -> QuerySpec:
    return QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=200.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURE_PATH)


def test_analyze_computes_deterministic_statistics(sample_spec, sample_df):
    """Proves analyzer computes exact profile counts, observation counts, date span, and variable stats."""
    fetch_result = FetchResult(
        status=FetchStatus.SUCCESS,
        data=sample_df,
        is_cached=False,
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )

    analysis = analyze(sample_df, sample_spec, fetch_result)

    assert analysis.profile_count == 2
    assert analysis.observation_count == 188
    assert analysis.date_start == "2022-01-04 05:41:20"
    assert analysis.date_end == "2022-01-06 01:28:30"

    # Per-variable min / mean / max
    assert "TEMP" in analysis.variable_stats
    temp_stat = analysis.variable_stats["TEMP"]
    assert temp_stat.observation_count == 188
    assert temp_stat.missing_count == 0
    assert temp_stat.min_value == pytest.approx(17.24, abs=0.05)
    assert temp_stat.max_value == pytest.approx(20.82, abs=0.05)
    assert temp_stat.mean_value is not None

    # Depth coverage per profile
    assert len(analysis.depth_coverage) == 2
    for p_depth in analysis.depth_coverage:
        assert p_depth.shallowest_depth >= 0.0
        assert p_depth.deepest_depth > 180.0
        assert p_depth.reached_requested_depth is True
    assert analysis.fraction_reaching_requested_depth == 1.0


def test_summary_text_contains_all_mandatory_elements(sample_spec, sample_df):
    """Proves summary_text always includes mode, QC filter, depth range, profiles, cache, and verification."""
    fetch_result = FetchResult(
        status=FetchStatus.SUCCESS,
        data=sample_df,
        is_cached=True,
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )

    analysis = analyze(sample_df, sample_spec, fetch_result)
    text = analysis.summary

    assert "Mode" in text and "`research`" in text
    assert "QC Filter in effect" in text
    assert get_qc_filter_description(DataMode.RESEARCH) in text
    assert analysis.qc_filter_description == get_qc_filter_description(DataMode.RESEARCH)
    assert "Effective depth range" in text and "0.0" in text and "200.0" in text
    assert "Profiles used" in text and "2" in text
    assert "Cached from local store" in text
    # When verified is True, warning notice is absent
    assert "profile count unverified" not in text

    # Observation mean is explicitly labeled as not depth-weighted
    assert "observation mean (not depth-weighted)" in text

    # Per-depth-bin statistics within effective depth (0-200 dbar)
    temp_bins = analysis.variable_stats["TEMP"].depth_bins
    assert len(temp_bins) >= 1
    assert any("0–100 dbar" in b.bin_label for b in temp_bins)
    assert any("100–200 dbar" in b.bin_label or "100–500 dbar" in b.bin_label for b in temp_bins)


def test_summary_text_flags_default_depth_and_unverified_profile_count(sample_df):
    """Proves default 0-500 dbar depth is explicitly flagged and unverified profile count is warned."""
    spec_no_depth = QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP],
        depth_range=None,  # triggers 0-500 dbar default
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )

    fetch_result = FetchResult(
        status=FetchStatus.SUCCESS,
        data=sample_df,
        is_cached=False,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=False,  # Unverified!
    )

    analysis = analyze(sample_df, spec_no_depth, fetch_result)
    text = analysis.summary

    assert "default 0–500 dbar applied" in text
    assert "profile count unverified" in text
    assert "Mode" in text and "`standard`" in text
    assert "QC=1 (good) and QC=2" in text
    assert "Fetched remotely from ERDDAP" in text


def test_analyze_handles_empty_dataset(sample_spec):
    """Proves analyze handles empty or None DataFrames without throwing exceptions."""
    empty_df = pd.DataFrame()
    fetch_result = FetchResult(
        status=FetchStatus.EMPTY,
        data=None,
        is_cached=False,
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )

    analysis = analyze(empty_df, sample_spec, fetch_result)
    assert analysis.profile_count == 0
    assert analysis.observation_count == 0
    assert analysis.summary != ""
    assert "Profiles used" in analysis.summary and "0" in analysis.summary
    assert "Observations" in analysis.summary and "0" in analysis.summary
