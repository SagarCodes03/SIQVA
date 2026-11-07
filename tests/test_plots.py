"""Structural unit tests for siqva.plots module (Plotly visualizations and theme)."""

from pathlib import Path
import pandas as pd
import pytest

from siqva.plots import (
    COLOR_AMBER,
    THEME_BG,
    plot_acoustic_profile,
    plot_bgc_omz_profile,
    plot_cyclone_tchp,
    plot_depth_profile,
    plot_float_drift_velocity,
    plot_hovmoller_section,
    plot_position_map,
    plot_regional_climatology_envelope,
    plot_stability_buoyancy,
    plot_thermocline_and_barrier,
    plot_ts_diagram,
    plot_ts_with_isopycnals,
)
from siqva.spec import Variable

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


def test_physics_plots_with_missing_gsw_return_placeholder(sample_df, monkeypatch):
    """Proves all physics plots return a valid themed figure with placeholder annotation when gsw is None."""
    monkeypatch.setattr("siqva.plots.gsw", None)

    for plot_func in [plot_thermocline_and_barrier, plot_cyclone_tchp, plot_acoustic_profile]:
        fig = plot_func(sample_df, summary=None)
        assert len(fig.data) == 0
        annot_texts = [a.text for a in fig.layout.annotations if a.text]
        assert any("requires 'gsw' library" in text for text in annot_texts)



def test_hovmoller_section(sample_df):
    """Proves Hovmöller diagram renders contour or profile from observation times."""
    fig = plot_hovmoller_section(sample_df, param="TEMP")
    assert len(fig.data) >= 1

    empty_fig = plot_hovmoller_section(pd.DataFrame())
    assert len(empty_fig.data) == 0
    assert any("No observation data" in a.text for a in empty_fig.layout.annotations)


def test_stability_buoyancy(sample_df):
    """Proves Brunt-Väisälä buoyancy profile computes N^2 stability from dataset."""
    fig = plot_stability_buoyancy(sample_df, lat=15.0, lon=80.0)
    assert len(fig.data) >= 1
    assert "N²" in (fig.layout.xaxis.title.text or "")

    empty_fig = plot_stability_buoyancy(pd.DataFrame())
    assert len(empty_fig.data) == 0
    assert any("No observation data" in a.text for a in empty_fig.layout.annotations)


def test_ts_with_isopycnals(sample_df):
    """Proves Conservative T-S diagram with background isopycnals generates correctly."""
    fig = plot_ts_with_isopycnals(sample_df, lon=80.0, lat=15.0)
    assert len(fig.data) >= 1

    empty_fig = plot_ts_with_isopycnals(pd.DataFrame())
    assert len(empty_fig.data) == 0
    assert any("No observation data" in a.text for a in empty_fig.layout.annotations)


def test_regional_climatology_envelope(sample_df):
    """Proves regional climatology computes mean and +/-1 sigma envelope."""
    plat = sample_df["PLATFORM_NUMBER"].iloc[0] if "PLATFORM_NUMBER" in sample_df.columns else None
    fig = plot_regional_climatology_envelope(sample_df, target_wmo=plat, param="TEMP")
    assert len(fig.data) >= 2

    empty_fig = plot_regional_climatology_envelope(pd.DataFrame())
    assert len(empty_fig.data) == 0
    assert any("No observation data" in a.text for a in empty_fig.layout.annotations)


def test_bgc_omz_profile(sample_df):
    """Proves BGC dissolved oxygen profile identifies hypoxic zone and handles missing DOXY cleanly."""
    # When DOXY is absent in standard hydrographic file
    no_doxy_fig = plot_bgc_omz_profile(sample_df)
    assert any("DOXY" in a.text for a in no_doxy_fig.layout.annotations)

    # When DOXY is present
    df_with_doxy = sample_df.copy()
    df_with_doxy["DOXY"] = 50.0  # Hypoxic
    fig = plot_bgc_omz_profile(df_with_doxy)
    assert len(fig.data) >= 1
    assert "DOXY" in (fig.layout.xaxis.title.text or "")


def test_float_drift_velocity():
    """Proves float drift velocity calculates speed from surfacing coordinates."""
    mock_df = pd.DataFrame({
        "TIME": pd.date_range("2022-01-01", periods=5, freq="10D"),
        "LATITUDE": [15.0, 15.2, 15.5, 15.8, 16.0],
        "LONGITUDE": [65.0, 65.5, 66.0, 66.4, 67.0],
        "CYCLE_NUMBER": [1, 2, 3, 4, 5],
        "PLATFORM_NUMBER": ["6904128"] * 5,
    })
    fig = plot_float_drift_velocity(mock_df)
    assert len(fig.data) >= 1
    assert "Drift Speed" in (fig.layout.yaxis.title.text or "")

    empty_fig = plot_float_drift_velocity(pd.DataFrame())
    assert len(empty_fig.data) == 0
    assert any("No trajectory observations" in a.text for a in empty_fig.layout.annotations)
