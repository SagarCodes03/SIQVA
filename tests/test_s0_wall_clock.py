"""Tests for S0: size guardrail bypass closure and foreground wall-clock budget."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from siqva.card import build_card, generate_script
from siqva.chunking import fetch_chunked
from siqva.fetcher import (
    DEFAULT_WALL_CLOCK_BUDGET,
    FetchMetadata,
    FetchResult,
    FetchStatus,
    get_wall_clock_budget,
)
from siqva.pipeline import PipelineStatus, run
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)


@pytest.fixture
def sample_chunk_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "PLATFORM_NUMBER": [1902345],
            "CYCLE_NUMBER": [1],
            "TIME": ["2022-01-15T12:00:00Z"],
            "LATITUDE": [12.5],
            "LONGITUDE": [64.5],
            "PRES": [10.0],
            "TEMP": [25.0],
        }
    )


def test_wall_clock_budget_default_and_env_override(monkeypatch):
    """Verify get_wall_clock_budget defaults to 90.0 and obeys SIQVA_WALL_CLOCK_BUDGET."""
    monkeypatch.delenv("SIQVA_WALL_CLOCK_BUDGET", raising=False)
    assert get_wall_clock_budget() == DEFAULT_WALL_CLOCK_BUDGET

    monkeypatch.setenv("SIQVA_WALL_CLOCK_BUDGET", "45.5")
    assert get_wall_clock_budget() == 45.5

    monkeypatch.setenv("SIQVA_WALL_CLOCK_BUDGET", "invalid")
    assert get_wall_clock_budget() == DEFAULT_WALL_CLOCK_BUDGET


def test_fetch_chunked_wall_clock_budget_exceeded(sample_chunk_df, tmp_path):
    """Verify that when the wall-clock budget is exceeded during chunked fetch, it returns TIMEOUT with progress details."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    call_count = 0

    def slow_fetch(chunk_spec, **kwargs):
        nonlocal call_count
        call_count += 1
        # First chunk succeeds, then time budget runs out
        meta = FetchMetadata(
            src="erddap",
            source="erddap",
            argopy_version="1.5.0",
            xarray_version="2026.9.0",
            fetch_timestamp="2026-11-07T12:00:00Z",
            row_count=len(sample_chunk_df),
            profile_count=1,
            data_hash="dummyhash",
            fetch_key=chunk_spec.fetch_key(),
        )
        return FetchResult(
            status=FetchStatus.SUCCESS,
            data=sample_chunk_df,
            is_cached=False,
            cache_key=chunk_spec.fetch_key(),
            metadata=meta,
            effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
            profile_count_verified=True,
            profile_count=1,
        )

    # Pass wall_clock_budget = 0.001s so loop exceeds budget immediately after chunk 1
    # We mock time.monotonic to advance by 5 seconds on each call
    time_points = [0.0, 0.1, 10.0, 20.0, 30.0]
    time_idx = 0

    def mock_monotonic():
        nonlocal time_idx
        val = time_points[min(time_idx, len(time_points) - 1)]
        time_idx += 1
        return val

    with patch("time.monotonic", side_effect=mock_monotonic):
        res = fetch_chunked(
            spec,
            cache_dir=tmp_path,
            fetcher_fn=slow_fetch,
            wall_clock_budget=5.0,
            max_request_size=None,
        )

    assert res.status == FetchStatus.TIMEOUT
    assert "exceeded the wall-clock budget" in res.error_message
    assert "remain cached" in res.error_message
    assert res.data is None


def test_guardrail_disabled_card_and_script_note(sample_chunk_df, monkeypatch):
    """Verify that when guardrails are bypassed, QueryCard records it and generate_script includes the note."""
    monkeypatch.setenv("SIQVA_DISABLE_SIZE_GUARDRAIL", "1")

    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-07T12:00:00Z",
        row_count=len(sample_chunk_df),
        profile_count=1,
        data_hash="dummyhash",
        fetch_key=spec.fetch_key(),
    )
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=sample_chunk_df,
        is_cached=False,
        cache_key=spec.fetch_key(),
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=1,
    )

    card = build_card(spec, fetch_res)
    assert card.guardrail_disabled is True

    script = generate_script(card)
    assert "Guardrails: Bypassed (SIQVA_DISABLE_SIZE_GUARDRAIL=1)" in script


def test_guardrail_enabled_by_default_card():
    """Verify that with normal settings, QueryCard records guardrail_disabled=False."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=None,
        is_cached=False,
        cache_key=spec.fetch_key(),
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=0,
    )
    card = build_card(spec, fetch_res)
    assert card.guardrail_disabled is False
