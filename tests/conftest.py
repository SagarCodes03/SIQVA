"""Pytest fixtures and configuration for SIQVA test suite."""

import os
from pathlib import Path
import pandas as pd
import pytest
import argopy

from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.spec import DepthRange

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_argo_standard.parquet"


class NetworkBlockedError(RuntimeError):
    """Raised when an offline test attempts to hit the network via argopy."""
    pass


@pytest.fixture(autouse=True)
def guard_argopy_network(monkeypatch):
    """Prevent tests from initiating live network connections through argopy unless RUN_NETWORK_TESTS=1."""
    if os.getenv("RUN_NETWORK_TESTS") == "1":
        return

    def _blocked_data_fetcher(*args, **kwargs):
        raise NetworkBlockedError(
            "Live network access disabled in test suite without RUN_NETWORK_TESTS=1 (argopy.DataFetcher invoked)"
        )

    def _blocked_index_fetcher(*args, **kwargs):
        raise NetworkBlockedError(
            "Live network access disabled in test suite without RUN_NETWORK_TESTS=1 (argopy.IndexFetcher invoked)"
        )

    monkeypatch.setattr(argopy, "DataFetcher", _blocked_data_fetcher)
    monkeypatch.setattr(argopy, "IndexFetcher", _blocked_index_fetcher)


@pytest.fixture
def sample_fetch_result() -> FetchResult:
    df_fixture = pd.read_parquet(FIXTURE_PATH)
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-07T12:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="dummyhash",
        fetch_key="dummykey",
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key="dummykey",
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )
