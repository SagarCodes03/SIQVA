"""Tests for plot observation capping, stratified sampling, determinism, and JSON payload size."""

import json
import numpy as np
import pandas as pd
import pytest

from siqva.plots import (
    MAX_PLOT_OBSERVATIONS,
    _stratified_sample_observations,
    plot_ts_diagram,
    plot_ts_with_isopycnals,
)


@pytest.fixture
def large_dataset() -> pd.DataFrame:
    """Create a realistic multi-profile dataset exceeding MAX_PLOT_OBSERVATIONS."""
    n_profiles = 20
    levels_per_profile = 500  # 10,000 total rows
    rows = []
    for p in range(n_profiles):
        wmo = 2900000 + p
        for cycle in [1, 2]:
            for z in np.linspace(5.0, 2000.0, levels_per_profile // 2):
                rows.append({
                    "PLATFORM_NUMBER": wmo,
                    "CYCLE_NUMBER": cycle,
                    "PRES": z,
                    "TEMP": 25.0 - 20.0 * (z / 2000.0) ** 0.5,
                    "PSAL": 35.0 + 1.0 * (z / 2000.0),
                    "LATITUDE": 15.0 + p * 0.1,
                    "LONGITUDE": 65.0 + p * 0.1,
                })
    return pd.DataFrame(rows)


def test_cap_and_annotation_applied_when_exceeding_max(large_dataset):
    """Verify that a dataset larger than MAX_PLOT_OBSERVATIONS is capped and annotated."""
    assert len(large_dataset) > MAX_PLOT_OBSERVATIONS

    fig = plot_ts_diagram(large_dataset)

    # Check trace observation count
    trace = fig.data[0]
    n_points = len(trace.x)
    assert n_points <= MAX_PLOT_OBSERVATIONS

    # Check annotation
    ann_texts = [ann.text for ann in fig.layout.annotations]
    expected_substr = f"Showing {n_points:,} of {len(large_dataset):,} observations (sampled)"
    assert any(expected_substr in t for t in ann_texts), f"Annotation not found in {ann_texts}"


def test_no_sampling_when_under_max(large_dataset):
    """Verify that datasets under MAX_PLOT_OBSERVATIONS are not sampled and have no sampled annotation."""
    small_df = large_dataset.iloc[:1000].copy()
    fig = plot_ts_diagram(small_df)

    trace = fig.data[0]
    assert len(trace.x) == 1000

    ann_texts = [ann.text for ann in fig.layout.annotations]
    assert not any("(sampled)" in t for t in ann_texts)


def test_sampling_is_deterministic(large_dataset):
    """Verify that stratified sampling is 100% deterministic across multiple invocations."""
    res1 = _stratified_sample_observations(large_dataset, max_points=MAX_PLOT_OBSERVATIONS)
    res2 = _stratified_sample_observations(large_dataset, max_points=MAX_PLOT_OBSERVATIONS)

    pd.testing.assert_frame_equal(res1, res2)

    fig1 = plot_ts_diagram(large_dataset)
    fig2 = plot_ts_diagram(large_dataset)

    assert list(fig1.data[0].x) == list(fig2.data[0].x)
    assert list(fig1.data[0].y) == list(fig2.data[0].y)


def test_stratified_sampling_covers_all_profiles(large_dataset):
    """Verify that stratified sampling retains observations from every profile."""
    sampled = _stratified_sample_observations(large_dataset, max_points=MAX_PLOT_OBSERVATIONS)

    original_profiles = set(zip(large_dataset["PLATFORM_NUMBER"], large_dataset["CYCLE_NUMBER"]))
    sampled_profiles = set(zip(sampled["PLATFORM_NUMBER"], sampled["CYCLE_NUMBER"]))

    assert sampled_profiles == original_profiles, "Every profile group must have representation"


def test_figure_json_size_reduction(large_dataset):
    """Measure and compare figure JSON size with and without capping."""
    fig_capped = plot_ts_diagram(large_dataset)
    json_capped = json.dumps(fig_capped.to_plotly_json())
    size_capped_kb = len(json_capped.encode("utf-8")) / 1024.0

    # Uncapped simulation (sending all rows)
    import plotly.graph_objects as go
    fig_uncapped = go.Figure(go.Scatter(
        x=large_dataset["PSAL"],
        y=large_dataset["TEMP"],
        mode="markers",
        marker=dict(color=large_dataset["PRES"])
    ))
    json_uncapped = json.dumps(fig_uncapped.to_plotly_json())
    size_uncapped_kb = len(json_uncapped.encode("utf-8")) / 1024.0

    assert size_capped_kb < size_uncapped_kb
    assert size_capped_kb < 200.0  # Well bounded for responsive browser rendering
