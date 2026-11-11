"""Tests for fetching sample profiles (Task S6: fetcher.fetch_sample)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from siqva.analyzer import analyze
from siqva.fetcher import (
    FetchResult,
    FetchStatus,
    compute_profile_cache_key,
    fetch_sample,
)
from siqva.floatindex import SamplePick, SampleSelection
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_argo_standard.parquet"


@pytest.fixture
def sample_spec() -> QuerySpec:
    return QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 31)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=200.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )


@pytest.fixture
def sample_picks() -> list[SamplePick]:
    return [
        SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True),
        SamplePick(wmo=2901002, cycle=2, date="2022-01-10", lat=12.0, lon=62.0, is_delayed=True),
        SamplePick(wmo=2901003, cycle=3, date="2022-01-15", lat=13.0, lon=63.0, is_delayed=True),
        SamplePick(wmo=2901004, cycle=4, date="2022-01-20", lat=14.0, lon=64.0, is_delayed=True),
    ]


class MockProfileEngine:
    """Mock argopy DataFetcher supporting profile() and region() calls."""

    def __init__(self, mode: str = "standard", src: str = "erddap", **kwargs):
        self.mode = mode
        self.src = src
        self.recorded_calls: list[tuple[int, int]] = []
        self.recorded_boxes: list[list] = []
        self._cur_wmo = None
        self._cur_cyc = None

    def profile(self, wmo, cyc):
        self.recorded_calls.append((wmo, cyc))
        self._cur_wmo = wmo
        self._cur_cyc = cyc
        return self

    def region(self, box):
        self.recorded_boxes.append(box)
        return self

    def to_dataframe(self):
        # Create a single profile DataFrame with matching PLATFORM_NUMBER and CYCLE_NUMBER
        df = pd.read_parquet(FIXTURE_PATH).copy()
        if self._cur_wmo is not None and self._cur_cyc is not None:
            df["PLATFORM_NUMBER"] = self._cur_wmo
            df["CYCLE_NUMBER"] = self._cur_cyc
            df["DATA_MODE"] = "D"
        return df


def test_call_count_equals_picks(tmp_path, sample_spec, sample_picks):
    """Verify that remote profile() is invoked exactly once per pick when cache is empty."""
    engine = MockProfileEngine()
    engine_factory = MagicMock(return_value=engine)

    res = fetch_sample(
        sample_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        fetcher_engine=engine_factory,
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.is_sample is True
    assert res.n_selected == len(sample_picks)
    assert len(engine.recorded_calls) == len(sample_picks)
    # Check recorded calls match the pick WMO and cycles
    expected_calls = [(p.wmo, p.cycle) for p in sample_picks]
    assert engine.recorded_calls == expected_calls


def test_profile_caching(tmp_path, sample_spec, sample_picks):
    """Verify that second fetch of identical picks loads from cache without remote calls."""
    engine1 = MockProfileEngine()
    fetch_sample(
        sample_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        fetcher_engine=MagicMock(return_value=engine1),
        pause_s=0.0,
    )
    assert len(engine1.recorded_calls) == len(sample_picks)

    # Second run against same cache_dir
    engine2 = MockProfileEngine()
    res2 = fetch_sample(
        sample_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        fetcher_engine=MagicMock(return_value=engine2),
        pause_s=0.0,
    )

    assert res2.status == FetchStatus.SUCCESS
    assert res2.is_cached is True
    # Zero remote calls on second fetch
    assert len(engine2.recorded_calls) == 0


def test_partial_failure(tmp_path, sample_spec, sample_picks):
    """When some profile fetches fail, return what succeeded and report partial failure."""
    class FailingProfileEngine(MockProfileEngine):
        def profile(self, wmo, cyc):
            # Fail on the second and fourth picks
            if wmo in (2901002, 2901004):
                raise RuntimeError("Remote server 503 error for float profile")
            return super().profile(wmo, cyc)

    engine = FailingProfileEngine()
    res = fetch_sample(
        sample_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        fetcher_engine=MagicMock(return_value=engine),
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.n_selected == 2  # 2 of 4 succeeded
    assert res.suggestion is not None
    assert "2 of 4 profiles fetched" in res.suggestion


def test_budget_exceeded(tmp_path, sample_spec, sample_picks):
    """When wall-clock budget is exceeded during fetch loop, stop and report timeout or partial success."""
    # Budget of 0 seconds guarantees timeout before remote fetch
    res = fetch_sample(
        sample_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        wall_clock_budget=0.0,
        fetcher_engine=MagicMock(return_value=MockProfileEngine()),
        pause_s=0.0,
    )

    assert res.status == FetchStatus.TIMEOUT
    assert "wall-clock budget" in (res.error_message or "").lower()


def test_qc_applied_research_mode(tmp_path, sample_spec, sample_picks):
    """In research mode, profiles without delayed-mode data (DATA_MODE != 'D') are rejected."""
    class RealtimeProfileEngine(MockProfileEngine):
        def to_dataframe(self):
            df = super().to_dataframe()
            # Return real-time data
            df["DATA_MODE"] = "R"
            return df

    research_spec = sample_spec.model_copy(update={"mode": DataMode.RESEARCH})
    res = fetch_sample(
        research_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        fetcher_engine=MagicMock(return_value=RealtimeProfileEngine()),
        pause_s=0.0,
    )

    # All were rejected because research mode requires delayed data
    assert res.status == FetchStatus.EMPTY
    assert res.n_selected == 0


def test_no_regional_statistics_on_samples(tmp_path, sample_spec, sample_picks):
    """Verify that analyzer does NOT compute regional aggregate statistics or physics on samples."""
    engine = MockProfileEngine()
    fetch_res = fetch_sample(
        sample_spec,
        picks=sample_picks,
        cache_dir=tmp_path,
        fetcher_engine=MagicMock(return_value=engine),
        pause_s=0.0,
    )

    # Analyze sample data
    analysis = analyze(fetch_res.data, sample_spec, fetch_res)

    assert analysis.is_sample is True
    # Regional aggregate variable stats must be empty
    assert len(analysis.variable_stats) == 0
    # Physics summaries must be empty
    assert len(analysis.physics_summaries) == 0
    # Summary text must have mandatory design label
    assert "Sample" in analysis.summary
    assert "profiles in this region and period, selected evenly across space and time. Not representative of the whole region." in analysis.summary


def test_fallback_to_tiny_box(tmp_path, sample_spec):
    """When profile() raises, fetch_sample falls back to tiny box and filters to WMO & cycle."""
    class FallbackEngine(MockProfileEngine):
        def profile(self, wmo, cyc):
            raise NotImplementedError("profile access point disabled; test fallback")

        def region(self, box):
            self.recorded_boxes.append(box)
            return self

        def to_dataframe(self):
            df = pd.read_parquet(FIXTURE_PATH).copy()
            df["PLATFORM_NUMBER"] = 2901001
            df["CYCLE_NUMBER"] = 1
            df["DATA_MODE"] = "D"
            return df

    single_pick = [SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True)]
    engine = FallbackEngine()

    res = fetch_sample(
        sample_spec,
        picks=single_pick,
        cache_dir=tmp_path,
        fetcher_engine=MagicMock(return_value=engine),
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.n_selected == 1
    # Verify fallback box was recorded
    assert len(engine.recorded_boxes) == 1
    # Box should be centered around lat 11.0, lon 61.0
    box = engine.recorded_boxes[0]
    assert 60.9 < box[0] < 61.1
    assert 10.9 < box[2] < 11.1
