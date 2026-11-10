"""Tests verifying offline safety, network guards, and call-time fetcher resolution."""

import time
from unittest.mock import patch
import pytest
import argopy

from siqva.fetcher import FetchResult, FetchStatus, fetch
from siqva.pipeline import run, run_spec
from siqva.spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable


def test_argopy_data_fetcher_raises_offline_fast():
    """Verify that invoking argopy.DataFetcher directly raises RuntimeError offline."""
    with pytest.raises(RuntimeError, match="Live network access disabled in test suite without RUN_NETWORK_TESTS=1"):
        argopy.DataFetcher(src="erddap")


def test_argopy_index_fetcher_raises_offline_fast():
    """Verify that invoking argopy.IndexFetcher directly raises RuntimeError offline."""
    with pytest.raises(RuntimeError, match="Live network access disabled in test suite without RUN_NETWORK_TESTS=1"):
        argopy.IndexFetcher(src="erddap")


def test_real_fetch_fails_fast_offline_without_network(tmp_path):
    """Verify that calling real fetch() without cache fails fast with clear error rather than hanging."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=100.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )
    start = time.perf_counter()
    res = fetch(spec, cache_dir=tmp_path, force_refresh=True)
    duration = time.perf_counter() - start

    assert duration < 2.0, f"Expected fetch to fail fast, took {duration:.2f}s"
    assert res.status == FetchStatus.ERROR
    assert "RUN_NETWORK_TESTS=1" in (res.error_message or "")


def test_pipeline_run_resolves_mock_pipeline_fetch(sample_fetch_result):
    """Verify that patch('siqva.pipeline.fetch') is dynamically resolved by pipeline.run."""
    with patch("siqva.pipeline.fetch", return_value=sample_fetch_result) as mock_p_fetch:
        res = run("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        assert mock_p_fetch.called
        assert res.status.value == "success"


def test_pipeline_run_resolves_mock_fetcher_fetch(sample_fetch_result):
    """Verify that patch('siqva.fetcher.fetch') is dynamically resolved by pipeline.run."""
    with patch("siqva.fetcher.fetch", return_value=sample_fetch_result) as mock_f_fetch:
        res = run("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        assert mock_f_fetch.called
        assert res.status.value == "success"

