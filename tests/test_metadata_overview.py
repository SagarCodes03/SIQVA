"""Tests for S4: Metadata and Float Position Overview Maps."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pandas as pd
import plotly.graph_objects as go
import pytest

from siqva.floatindex import FloatIndex
from siqva.parser import parse, parse_detailed
from siqva.pipeline import PipelineStatus, run, run_spec
from siqva.plots import (
    DEFAULT_MAX_MARKER_FLOATS,
    DEFAULT_MAX_TRACKS_FLOATS,
    render_index_overview_map,
)
from siqva.spec import BoundingBox, DateRange, Intent, QuerySpec, Variable


@pytest.fixture
def synthetic_index():
    """Create a synthetic FloatIndex spanning Indian and Pacific (antimeridian) oceans."""
    df = pd.DataFrame(
        {
            "wmo": [1001, 1001, 1002, 2001, 2001, 2002],
            "cycle": [1, 2, 1, 1, 2, 1],
            "cycle_number": [1, 2, 1, 1, 2, 1],
            "latitude": [10.0, 11.0, 12.0, 5.0, 6.0, -5.0],
            "longitude": [65.0, 66.0, 67.0, 178.0, -178.0, 175.0],  # 2001 & 2002 in Pacific crossing 180°
            "date": pd.to_datetime([
                "2023-01-01", "2023-01-10", "2023-01-05",
                "2023-01-02", "2023-01-12", "2023-01-06",
            ]),
            "ocean": ["I", "I", "I", "P", "P", "P"],
            "is_delayed": [True, True, False, True, True, False],
            "institution": ["IN", "IN", "IN", "AO", "AO", "AO"],
        }
    )
    meta = {
        "build_date": "2023-02-01T00:00:00Z",
        "min_date": "2023-01-01",
        "max_date": "2023-01-15",
    }
    return FloatIndex(df=df, metadata=meta)


def test_float_location_query_parsing():
    """Verify float location questions parse to Intent.MAP without requiring dates or variables."""
    # 1. "show floats in the Indian Ocean"
    outcome_io = parse_detailed("show floats in the Indian Ocean", allow_llm=False)
    assert outcome_io.is_success is True
    assert outcome_io.spec is not None
    assert outcome_io.spec.intent == Intent.MAP
    assert outcome_io.spec.date_range is not None
    assert outcome_io.provenance.get("date_range") == "default"
    assert outcome_io.provenance.get("variables") == "default"

    # 2. "map of floats in the Pacific"
    outcome_pac = parse_detailed("map of floats in the Pacific", allow_llm=False)
    assert outcome_pac.is_success is True
    assert outcome_pac.spec is not None
    assert outcome_pac.spec.intent == Intent.MAP
    assert outcome_pac.spec.basin == "Pacific Ocean"
    assert outcome_pac.spec.region is None

    # 3. "how many floats in the Arabian Sea"
    outcome_as = parse_detailed("how many floats in the Arabian Sea", allow_llm=False)
    assert outcome_as.is_success is True
    assert outcome_as.spec is not None
    assert outcome_as.spec.intent == Intent.MAP
    assert outcome_as.spec.region is not None


def test_fetcher_not_called_in_pipeline():
    """Verify that metadata (Float Position Map) queries do NOT call the remote fetcher."""
    with patch("siqva.pipeline.fetch") as spy_pipe_fetch, patch("siqva.fetcher.fetch") as spy_fetcher_fetch:
        res = run("show floats in the Indian Ocean")
        assert res.status == PipelineStatus.SUCCESS
        assert "map" in res.figures
        assert isinstance(res.figures["map"], go.Figure)

        # Neither fetcher was called!
        spy_pipe_fetch.assert_not_called()
        spy_fetcher_fetch.assert_not_called()


def test_indian_ocean_and_pacific_antimeridian_on_synthetic_index(synthetic_index):
    """Verify rendering on Indian Ocean and Pacific (antimeridian) using synthetic index."""
    # 1. Indian Ocean
    spec_io = QuerySpec(
        basin="Indian Ocean",
        date_range=DateRange(start="2023-01-01", end="2023-01-15"),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )
    fig_io, render_time_io, desc_io = render_index_overview_map(synthetic_index, spec_io)
    assert isinstance(fig_io, go.Figure)
    assert render_time_io >= 0.0
    assert "trajectory tracks" in desc_io.lower()
    assert len(fig_io.data) == 2  # 2 floats: WMO 1001 and 1002

    # 2. Pacific Ocean crossing antimeridian
    spec_pac = QuerySpec(
        basin="Pacific Ocean",
        date_range=DateRange(start="2023-01-01", end="2023-01-15"),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )
    fig_pac, render_time_pac, desc_pac = render_index_overview_map(synthetic_index, spec_pac)
    assert isinstance(fig_pac, go.Figure)
    assert len(fig_pac.data) == 2  # 2 floats: WMO 2001 and 2002


def test_display_modes_tracks_markers_and_coarse_grid():
    """Verify transitions between tracks (<= 50), markers (<= 5000), and coarse grid (> 5000)."""
    # 1. Regime 1: Tracks (3 floats)
    df_small = pd.DataFrame(
        {
            "wmo": [1, 1, 2, 3],
            "cycle": [1, 2, 1, 1],
            "cycle_number": [1, 2, 1, 1],
            "latitude": [10.0, 11.0, 12.0, 13.0],
            "longitude": [60.0, 61.0, 62.0, 63.0],
            "date": pd.to_datetime(["2023-01-01", "2023-01-05", "2023-01-02", "2023-01-03"]),
            "ocean": ["I", "I", "I", "I"],
            "is_delayed": [True, True, True, True],
            "institution": ["AO", "AO", "AO", "AO"],
        }
    )
    idx_small = FloatIndex(df=df_small)
    spec = QuerySpec(
        basin="Indian Ocean",
        date_range=DateRange(start="2023-01-01", end="2023-01-10"),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )
    fig_tracks, _, desc_tracks = render_index_overview_map(idx_small, spec, max_tracks=50)
    assert "trajectory tracks" in desc_tracks.lower()

    # 2. Regime 2: Markers (max_tracks=2, so 3 floats exceeds track limit)
    fig_markers, _, desc_markers = render_index_overview_map(idx_small, spec, max_tracks=2, max_markers=100)
    assert "last observed positions" in desc_markers.lower()
    assert len(fig_markers.data) == 1  # single Scattergeo trace with markers

    # 3. Regime 3: Coarse Grid (> max_markers, e.g. max_markers=2)
    fig_grid, _, desc_grid = render_index_overview_map(idx_small, spec, max_tracks=1, max_markers=2)
    assert "density grid" in desc_grid.lower()
    assert len(fig_grid.data) == 1
    # Check that grid marker has colorbar
    assert fig_grid.data[0].marker.showscale is True


def test_answer_text_contains_metadata():
    """Verify answer text summary includes snapshot date, age, exact counts, and render time."""
    res = run("how many floats in the Arabian Sea")
    assert res.status == PipelineStatus.SUCCESS
    assert res.analysis is not None
    summary = res.analysis.summary

    assert "**Active Floats**:" in summary
    assert "**Total Profiles**:" in summary
    assert "**Index Snapshot**:" in summary
    assert "**Map Render Time**:" in summary
    assert res.card is not None
    assert res.card.src == "float_index"


def test_missing_index_gives_clear_message_without_fetcher():
    """Verify that when the float index is unavailable, pipeline returns clear error without fetcher."""
    with patch("siqva.pipeline.load_float_index", return_value=None), \
         patch("siqva.pipeline.fetch") as spy_pipe_fetch:
        spec = QuerySpec(
            basin="Indian Ocean",
            date_range=DateRange(start="2023-01-01", end="2023-01-10"),
            variables=[Variable.TEMP],
            intent=Intent.MAP,
        )
        res = run_spec(spec)
        assert res.status == PipelineStatus.ERROR
        assert "float index" in res.error_message.lower()
        spy_pipe_fetch.assert_not_called()
