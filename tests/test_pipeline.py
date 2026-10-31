"""Unit tests for siqva.pipeline module."""

from datetime import date
from pathlib import Path
import pandas as pd
import pytest

from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.pipeline import PipelineResult, PipelineStatus, run, run_spec
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


@pytest.fixture
def sample_spec() -> QuerySpec:
    return QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )


@pytest.fixture
def mock_fetch_result(sample_spec) -> FetchResult:
    df = pd.read_parquet(FIXTURE_PATH)
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.4.0",
        xarray_version="2025.9.0",
        fetch_timestamp="2024-01-15T12:00:00Z",
        row_count=len(df),
        profile_count=2,
        data_hash="abc123pipelinehash",
        fetch_key=sample_spec.fetch_key(),
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=False,
        cache_key=sample_spec.fetch_key(),
        metadata=meta,
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )


def test_pipeline_clarification_needed():
    """Proves pipeline halts cleanly and requests clarification when query is ambiguous."""
    res = run("salinity profiles in North Atlantic in March", allow_llm=False)
    assert res.status == PipelineStatus.CLARIFICATION_NEEDED
    assert res.clarification is not None
    assert "date_range" in res.clarification.ambiguous_fields
    assert res.card is None


def test_pipeline_run_spec_success(tmp_path, sample_spec, mock_fetch_result):
    """Proves run_spec generates figures, analysis, cards, and scripts deterministically."""
    db_file = tmp_path / "test_pipeline.sqlite"
    res = run_spec(
        sample_spec,
        fetcher_fn=lambda *a, **kw: mock_fetch_result,
        db_path=db_file,
    )

    assert res.status == PipelineStatus.SUCCESS
    assert res.is_success is True
    assert res.spec == sample_spec
    assert res.analysis is not None
    assert res.card is not None
    assert res.script is not None
    assert "map" in res.figures
    assert "profile" in res.figures
    assert "ts" in res.figures
    assert "box = [-30.0, -28.0, 32.0, 34.0, 0.0, 500.0" in res.script


def test_pipeline_empty_fetch(sample_spec):
    """Proves pipeline handles empty remote fetches gracefully without crashing."""
    empty_result = FetchResult(
        status=FetchStatus.EMPTY,
        data=None,
        is_cached=False,
        cache_key=sample_spec.fetch_key(),
        error_message="No profiles found matching constraints.",
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )

    res = run_spec(
        sample_spec,
        fetcher_fn=lambda *a, **kw: empty_result,
    )

    assert res.status == PipelineStatus.EMPTY
    assert res.is_success is False
    assert "No profiles found" in res.error_message
    assert res.card is None

