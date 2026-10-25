"""Structural unit tests for argocard.plots module (Plotly visualizations and theme)."""

from pathlib import Path
import pandas as pd
import pytest

from argocard.plots import (
    COLOR_AMBER,
    THEME_BG,
    plot_depth_profile,
    plot_position_map,
    plot_ts_diagram,
)
from argocard.spec import Variable

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURE_PATH)


def test_depth_profile_structure(sample_df):
    """Proves depth profile has inverted y-axis, correct titles, and one trace per profile."""
    fig = plot_depth_profile(sample_df, variable=Variable.TEMP)

    # 2 profiles in sample fixture -> 2 line traces
    assert len(fig.data) == 2
    for trace in fig.data:
        assert trace.mode == "lines"

    # Inverted pressure axis
    assert fig.layout.yaxis.autorange == "reversed"
    assert "Pressure" in (fig.layout.yaxis.title.text or "")
    assert "TEMP" in (fig.layout.xaxis.title.text or "")

    # Dark theme
    assert fig.layout.paper_bgcolor == THEME_BG


def test_depth_profile_capping_and_annotation(sample_df):
    """Proves profile capping restricts traces and displays visible warning note."""
    fig = plot_depth_profile(sample_df, variable=Variable.TEMP, max_profiles=1)

    # Capped at 1 trace
    assert len(fig.data) == 1

    # Annotation present mentioning capping
    annot_texts = [a.text for a in fig.layout.annotations if a.text]
    assert any("capped" in text.lower() or "showing 1 of 2" in text.lower() for text in annot_texts)


def test_depth_profile_handles_empty_and_single_profile(sample_df):
    """Proves empty and single-profile datasets are handled without exceptions."""
    # Empty
    empty_fig = plot_depth_profile(pd.DataFrame(), variable=Variable.TEMP)
    assert len(empty_fig.data) == 0
    assert any("No profile data" in a.text for a in empty_fig.layout.annotations)
    assert empty_fig.layout.yaxis.autorange == "reversed"

    # Single profile
    single_df = sample_df[sample_df["PLATFORM_NUMBER"] == sample_df["PLATFORM_NUMBER"].iloc[0]]
    single_fig = plot_depth_profile(single_df, variable=Variable.PSAL)
    assert len(single_fig.data) == 1
    assert "PSAL" in (single_fig.layout.xaxis.title.text or "")


def test_ts_diagram_structure(sample_df):
    """Proves T-S diagram has Salinity on X, Temp on Y, marker mode, and pressure coloring."""
    fig = plot_ts_diagram(sample_df)

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.mode == "markers"
    assert "Salinity" in (fig.layout.xaxis.title.text or "")
    assert "Temperature" in (fig.layout.yaxis.title.text or "")
    assert trace.marker.colorscale is not None


def test_ts_diagram_empty():
    """Proves T-S diagram handles empty datasets cleanly."""
    fig = plot_ts_diagram(pd.DataFrame())
    assert len(fig.data) == 0
    assert any("No observation data" in a.text for a in fig.layout.annotations)


def test_position_map_structure(sample_df):
    """Proves position map draws scattergeo traces and highlights selected profile in amber."""
    # Base map
    fig = plot_position_map(sample_df)
    assert len(fig.data) >= 1
    assert fig.data[0].type == "scattergeo"

    # With selected profile highlight
    plat = sample_df["PLATFORM_NUMBER"].iloc[0]
    cyc = sample_df["CYCLE_NUMBER"].iloc[0]
    fig_highlight = plot_position_map(sample_df, selected_profile=(plat, cyc))
    assert len(fig_highlight.data) == len(fig.data) + 1
    star_trace = fig_highlight.data[-1]
    assert star_trace.marker.color == COLOR_AMBER
    assert star_trace.marker.symbol == "star"


def test_position_map_empty():
    """Proves position map handles empty dataset without crash."""
    fig = plot_position_map(pd.DataFrame())
    assert len(fig.data) == 0
    assert any("No position data" in a.text for a in fig.layout.annotations)
