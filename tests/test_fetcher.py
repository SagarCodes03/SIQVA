"""Unit and offline tests for argocard.fetcher module, caching, and error handling."""

import json
import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from argocard.fetcher import (
    DEFAULT_CACHE_DIR,
    DEFAULT_MAX_PROFILE_COUNT,
    CoverageStatus,
    FetchMetadata,
    FetchResult,
    FetchStatus,
    SnapshotProfileResult,
    count_profiles_in_snapshot,
    fetch,
)
from argocard.validator import DEFAULT_MAX_REQUEST_SIZE
from argocard.spec import (
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
        depth_range=DepthRange(min_depth=0.0, max_depth=200.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )


class MockEngine:
    """Mock argopy DataFetcher engine that returns a recorded fixture without hitting the network."""

    def __init__(self, mode: str = "", src: str = "erddap", api_timeout: int = 60, **kwargs):
        self.mode = mode
        self.src = src
        self.api_timeout = api_timeout
        self.recorded_box = None

    def region(self, box):
        self.recorded_box = box
        return self

    def to_dataframe(self):
        return pd.read_parquet(FIXTURE_PATH)


def test_fetch_cache_miss_creates_parquet_and_sidecar(tmp_path, sample_spec):
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    res = fetch(sample_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)

    assert res.status == FetchStatus.SUCCESS
    assert not res.is_cached
    assert res.data is not None
    assert len(res.data) == 188
    assert res.qc_report is not None
    assert res.metadata is not None

    # Verify cache files were created on disk
    fetch_key = sample_spec.fetch_key()
    parquet_file = tmp_path / f"{fetch_key}.parquet"
    json_file = tmp_path / f"{fetch_key}.json"

    assert parquet_file.exists()
    assert json_file.exists()

    # Verify sidecar metadata fields
    with open(json_file, "r", encoding="utf-8") as f:
        meta_data = json.load(f)

    assert meta_data["src"] == "erddap"
    assert meta_data["source"] == "erddap"
    assert "argopy_version" in meta_data
    assert "xarray_version" in meta_data
    assert meta_data["row_count"] == 188
    assert meta_data["profile_count"] == 2
    assert "data_hash" in meta_data
    assert meta_data["fetch_key"] == fetch_key


def test_fetch_cache_hit_labels_cached_and_bypasses_engine(tmp_path, sample_spec):
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # First fetch (cache miss)
    res1 = fetch(sample_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert res1.status == FetchStatus.SUCCESS
    assert not res1.is_cached
    assert mock_engine.call_count == 1

    # Second fetch (cache hit)
    res2 = fetch(sample_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert res2.status == FetchStatus.SUCCESS
    assert res2.is_cached  # Explicitly labelled as cached
    assert res2.data is not None
    assert len(res2.data) == 188
    assert res2.metadata.data_hash == res1.metadata.data_hash
    # Mock engine should NOT have been called again on cache hit
    assert mock_engine.call_count == 1


def test_fetch_passes_mode_explicitly_from_spec(tmp_path):
    recorded_modes = []

    def tracking_mock_engine(**kwargs):
        recorded_modes.append(kwargs.get("mode"))
        return MockEngine(**kwargs)

    for test_mode in [DataMode.RESEARCH, DataMode.STANDARD, DataMode.EXPERT]:
        spec = QuerySpec(
            region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
            date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
            variables=[Variable.TEMP],
            mode=test_mode,
            intent=Intent.PROFILE,
        )
        fetch(spec, cache_dir=tmp_path, force_refresh=True, fetcher_engine=tracking_mock_engine)
        assert recorded_modes[-1] == test_mode.value


def test_fetch_oversized_request_returns_clean_error(sample_spec):
    # Spec exceeding max_request_size: e.g. 60 deg * 40 deg over 365 days
    oversized = QuerySpec(
        region=BoundingBox(lon_min=20.0, lon_max=80.0, lat_min=-10.0, lat_max=30.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2023, 1, 1)),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )

    res = fetch(oversized)
    assert res.status == FetchStatus.OVERSIZED
    assert res.data is None
    assert "exceeds the maximum limit" in (res.error_message or "")
    assert "Please narrow your query" in (res.suggestion or "")


def test_fetch_empty_result_handled_cleanly(tmp_path, sample_spec):
    class EmptyEngine:
        def __init__(self, **kwargs):
            pass

        def region(self, box):
            return self

        def to_dataframe(self):
            # Simulate ERDDAP 404 / no data
            raise FileNotFoundError("https://erddap.ifremer.fr/erddap/tabledap/ArgoFloats.nc (404 Not Found)")

    res = fetch(sample_spec, cache_dir=tmp_path, force_refresh=True, fetcher_engine=EmptyEngine)
    assert res.status == FetchStatus.EMPTY
    assert res.data is None
    assert "No Argo profiles found" in (res.error_message or "")
    assert "Try widening" in (res.suggestion or "")


def test_fetch_timeout_handled_cleanly(tmp_path, sample_spec):
    class TimeoutEngine:
        def __init__(self, **kwargs):
            pass

        def region(self, box):
            return self

        def to_dataframe(self):
            raise TimeoutError("Connection to remote server timed out after 60s")

    res = fetch(sample_spec, cache_dir=tmp_path, force_refresh=True, fetcher_engine=TimeoutEngine)
    assert res.status == FetchStatus.TIMEOUT
    assert res.data is None
    assert "timed out" in (res.error_message or "").lower()


def test_fetch_force_refresh_bypasses_cache(tmp_path, sample_spec):
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # First fetch
    fetch(sample_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert mock_engine.call_count == 1

    # Second fetch with force_refresh=True
    res = fetch(sample_spec, cache_dir=tmp_path, force_refresh=True, fetcher_engine=mock_engine)
    assert mock_engine.call_count == 2
    assert not res.is_cached


# --- Additional Unit Tests for Profile Counting, Cache Expiry, and DMQC Empty Guidance ---


def test_profile_counting_avoids_single_cycle_bug():
    """Verify that multiple platforms sharing the same cycle number are counted as separate profiles."""
    df_shared_cycles = pd.DataFrame({
        "PLATFORM_NUMBER": [6904128, 6904128, 6901996, 6901996],
        "CYCLE_NUMBER": [5, 5, 5, 5],  # Both platforms are at cycle 5!
        "PRES": [10.0, 20.0, 10.0, 20.0],
        "TEMP": [15.0, 14.0, 15.2, 14.1],
    })

    # The buggy calculation was df['CYCLE_NUMBER'].nunique(), which returns 1
    assert df_shared_cycles["CYCLE_NUMBER"].nunique() == 1

    # The corrected count_unique_profiles returns 2
    from argocard.fetcher import count_unique_profiles
    assert count_unique_profiles(df_shared_cycles) == 2


def test_cache_expiry_standard_and_expert_modes(tmp_path, sample_spec):
    """Standard and expert entries expire after cache_expiry_days (default 7 days)."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Initial fetch writes cache
    ref_time_t0 = datetime(2024, 1, 1, 12, 0, 0)
    res1 = fetch(sample_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert mock_engine.call_count == 1
    assert not res1.is_cached

    # Manually back-date the sidecar timestamp by 8 days (exceeding default 7-day limit)
    sidecar_path = tmp_path / f"{sample_spec.fetch_key()}.json"
    with open(sidecar_path, "r", encoding="utf-8") as f:
        meta_dict = json.load(f)
    meta_dict["fetch_timestamp"] = "2024-01-01T00:00:00Z"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f)

    # Fetch at day 8 with default 7-day expiry -> Expired! Mock engine called again
    time_day_8 = datetime(2024, 1, 9, 0, 0, 0)
    res2 = fetch(sample_spec, cache_dir=tmp_path, reference_time=time_day_8, fetcher_engine=mock_engine)
    assert not res2.is_cached
    assert mock_engine.call_count == 2

    # If cache_expiry_days is set to 15 days, it is still valid -> Cache hit!
    # Re-backdate to day 1
    meta_dict["fetch_timestamp"] = "2024-01-01T00:00:00Z"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f)

    res3 = fetch(
        sample_spec,
        cache_dir=tmp_path,
        cache_expiry_days=15,
        reference_time=time_day_8,
        fetcher_engine=mock_engine,
    )
    assert res3.is_cached
    assert mock_engine.call_count == 2


def test_cache_expiry_research_mode_never_expires_unless_argopy_version_changes(tmp_path):
    """Research mode entries do not expire over time, but invalidate if argopy version changes."""
    research_spec = QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Initial fetch in research mode
    res1 = fetch(research_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert mock_engine.call_count == 1
    assert not res1.is_cached

    # Back-date the sidecar by 50 days (within 90-day research window)
    sidecar_path = tmp_path / f"{research_spec.fetch_key()}.json"
    with open(sidecar_path, "r", encoding="utf-8") as f:
        meta_dict = json.load(f)
    meta_dict["fetch_timestamp"] = "2024-01-01T00:00:00Z"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f)

    # 50 days later: Within 90-day window and matching argopy version -> Cache hit
    time_future = datetime(2024, 2, 20, 0, 0, 0)
    res2 = fetch(research_spec, cache_dir=tmp_path, reference_time=time_future, fetcher_engine=mock_engine)
    assert res2.is_cached
    assert mock_engine.call_count == 1

    # But if argopy version in sidecar differs from current: it invalidates!
    meta_dict["argopy_version"] = "0.9.9"  # older version
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f)

    res3 = fetch(research_spec, cache_dir=tmp_path, reference_time=time_future, fetcher_engine=mock_engine)
    assert not res3.is_cached
    assert mock_engine.call_count == 2


def test_empty_research_fetch_within_last_12_months_suggests_standard_mode(tmp_path):
    """When a research fetch is empty and ends within the last 12 months, suggest standard mode."""
    class EmptyEngine:
        def __init__(self, **kwargs):
            pass
        def region(self, box):
            return self
        def to_dataframe(self):
            raise FileNotFoundError("404 Not Found")

    ref_today = date(2024, 6, 1)

    # Window ending 60 days before today (within 12 months)
    recent_research_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2024, 3, 1), end=date(2024, 4, 1)),
        variables=[Variable.TEMP],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    res = fetch(recent_research_spec, cache_dir=tmp_path, today=ref_today, fetcher_engine=EmptyEngine)
    assert res.status == FetchStatus.EMPTY
    assert "delayed-mode" in res.error_message.lower()
    assert "DMQC" in res.error_message
    assert "standard mode" in res.suggestion.lower()
    assert "real-time" in res.suggestion.lower()


def test_empty_research_fetch_older_than_12_months_gives_standard_guidance(tmp_path):
    """When a research fetch is empty and ends >12 months ago, give standard spatial/temporal widening message."""
    class EmptyEngine:
        def __init__(self, **kwargs):
            pass
        def region(self, box):
            return self
        def to_dataframe(self):
            raise FileNotFoundError("404 Not Found")

    ref_today = date(2024, 6, 1)

    # Window ending 2 years before today
    old_research_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2021, 1, 1), end=date(2021, 2, 1)),
        variables=[Variable.TEMP],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    res = fetch(old_research_spec, cache_dir=tmp_path, today=ref_today, fetcher_engine=EmptyEngine)
    assert res.status == FetchStatus.EMPTY
    assert "No Argo profiles found" in res.error_message
    assert "widening" in res.suggestion.lower()



def test_fetch_defaults_depth_range_to_0_500_dbar(tmp_path):
    """When spec has no depth_range, fetch defaults to 0-500 dbar and reports it."""
    spec_no_depth = QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP],
        depth_range=None,
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )

    recorded_engines = []

    def recording_engine(**kw):
        eng = MockEngine(**kw)
        recorded_engines.append(eng)
        return eng

    res = fetch(spec_no_depth, cache_dir=tmp_path, fetcher_engine=recording_engine)

    assert res.status == FetchStatus.SUCCESS
    # Result shows defaulted depth range
    assert res.effective_depth_range == DepthRange(min_depth=0.0, max_depth=500.0)
    # Recorded engine received 0.0, 500.0 in the box
    assert recorded_engines[0].recorded_box[4] == 0.0
    assert recorded_engines[0].recorded_box[5] == 500.0


def test_pre_fetch_profile_count_rejection_via_index_fetcher(tmp_path, sample_spec):
    """When IndexFetcher pre-fetch count exceeds max_profile_count, reject before downloading data."""
    class MockIndexFetcher:
        def __init__(self, **kwargs):
            pass
        def region(self, box):
            return self
        def to_dataframe(self):
            # Simulate an index returning 45 profiles
            return pd.DataFrame({"file": [f"prof_{i}.nc" for i in range(45)]})

    mock_data_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Threshold set to 20 profiles, index reports 45 profiles -> Rejection!
    res = fetch(
        sample_spec,
        cache_dir=tmp_path,
        max_profile_count=20,
        fetcher_engine=mock_data_engine,
        index_fetcher_cls=MockIndexFetcher,
    )

    assert res.status == FetchStatus.OVERSIZED
    assert res.data is None
    assert "Estimated profile count (45)" in res.error_message
    assert "maximum limit (20)" in res.error_message
    assert "smaller region" in res.suggestion
    assert "shorter date window" in res.suggestion
    assert "shallower depth range" in res.suggestion
    # Heavy data fetcher was NOT called
    assert mock_data_engine.call_count == 0


def test_research_cache_expiry_90_days(tmp_path):
    """Research mode entries expire after 90 days in addition to the argopy version rule."""
    research_spec = QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Initial fetch writes cache
    res1 = fetch(research_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert mock_engine.call_count == 1
    assert not res1.is_cached

    sidecar_path = tmp_path / f"{research_spec.fetch_key()}.json"
    with open(sidecar_path, "r", encoding="utf-8") as f:
        meta_dict = json.load(f)
    meta_dict["fetch_timestamp"] = "2024-01-01T00:00:00Z"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f)

    # 60 days later: Within 90-day research cache window -> Cache hit!
    time_day_60 = datetime(2024, 3, 1, 0, 0, 0)
    res2 = fetch(research_spec, cache_dir=tmp_path, reference_time=time_day_60, fetcher_engine=mock_engine)
    assert res2.is_cached
    assert mock_engine.call_count == 1

    # 95 days later: Exceeds 90-day research cache window -> Expired! Re-fetches
    time_day_95 = datetime(2024, 4, 5, 0, 0, 0)
    res3 = fetch(research_spec, cache_dir=tmp_path, reference_time=time_day_95, fetcher_engine=mock_engine)
    assert not res3.is_cached
    assert mock_engine.call_count == 2


def test_both_guards_active_by_default(tmp_path):
    """Proves both cost limit (15,000) and profile count limit (100) are active by default."""
    assert DEFAULT_MAX_REQUEST_SIZE == 15_000.0
    assert DEFAULT_MAX_PROFILE_COUNT == 100

    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # (1) Test cost guard active by default without passing max_request_size:
    # 20 deg x 20 deg = 400 deg2, 40 days, depth 0-500 -> 400 * 40 * 1 = 16,000 > 15,000
    cost_oversized_spec = QuerySpec(
        region=BoundingBox(lon_min=0.0, lon_max=20.0, lat_min=0.0, lat_max=20.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 2, 10)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    # Default call without max_request_size
    res_cost = fetch(cost_oversized_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)
    assert res_cost.status == FetchStatus.OVERSIZED
    assert "exceeds the maximum limit" in (res_cost.error_message or "")
    assert mock_engine.call_count == 0

    # (2) Test profile count guard active by default without passing max_profile_count:
    # Small box: 2 deg x 2 deg, 5 days (cost = 2 * 2 * 5 = 20 << 15,000)
    small_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=62.0, lat_min=10.0, lat_max=12.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 6)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    # Create a local snapshot with 105 profiles (exceeds DEFAULT_MAX_PROFILE_COUNT = 100)
    snapshot_path = tmp_path / "test_snapshot.parquet"
    mock_profiles = pd.DataFrame({
        "wmo": [6900000 + i for i in range(105)],
        "cycle_number": [1] * 105,
        "latitude": [11.0] * 105,
        "longitude": [61.0] * 105,
        "date": [pd.Timestamp("2022-01-03")] * 105,
    })
    mock_profiles.to_parquet(snapshot_path, index=False)
    with open(tmp_path / "test_snapshot.json", "w", encoding="utf-8") as f:
        json.dump({
            "bbox": [60.0, 62.0, 10.0, 12.0],
            "min_date": "2022-01-01",
            "max_date": "2022-01-06",
            "fetch_date": "2022-01-10T00:00:00Z",
            "row_count": 105,
        }, f)

    # Default call without max_profile_count
    res_prof = fetch(
        small_spec,
        cache_dir=tmp_path,
        float_index_path=snapshot_path,
        fetcher_engine=mock_engine,
    )
    assert res_prof.status == FetchStatus.OVERSIZED
    assert "exceeds the maximum limit (100)" in (res_prof.error_message or "")
    assert mock_engine.call_count == 0


def test_request_over_cost_limit_returns_oversized_with_narrowing_suggestion(tmp_path):
    """Proves a request exceeding the cost limit returns OVERSIZED with narrowing suggestion."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Cost = 30 * 30 * 20 * (500 / 500) = 18,000 > 15,000
    oversized_spec = QuerySpec(
        region=BoundingBox(lon_min=10.0, lon_max=40.0, lat_min=0.0, lat_max=30.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 21)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )

    res = fetch(oversized_spec, cache_dir=tmp_path, fetcher_engine=mock_engine)

    assert res.status == FetchStatus.OVERSIZED
    assert res.data is None
    assert "exceeds the maximum limit (15,000.0)" in (res.error_message or "")
    assert "shrinking the bounding box" in (res.suggestion or "")
    assert "narrowing the date range" in (res.suggestion or "")
    assert "shallower depth range" in (res.suggestion or "")
    assert mock_engine.call_count == 0


def test_request_over_profile_limit_returns_oversized_with_narrowing_suggestion(tmp_path):
    """Proves a request exceeding the profile limit returns OVERSIZED with narrowing suggestion."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Well within cost cap (area = 4, days = 5 -> cost = 20)
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=62.0, lat_min=10.0, lat_max=12.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 6)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )

    # Local snapshot with 120 profiles
    snapshot_path = tmp_path / "test_snapshot.parquet"
    mock_profiles = pd.DataFrame({
        "wmo": [6900000 + i for i in range(120)],
        "cycle_number": [1] * 120,
        "latitude": [11.0] * 120,
        "longitude": [61.0] * 120,
        "date": [pd.Timestamp("2022-01-03")] * 120,
    })
    mock_profiles.to_parquet(snapshot_path, index=False)
    with open(tmp_path / "test_snapshot.json", "w", encoding="utf-8") as f:
        json.dump({
            "bbox": [60.0, 62.0, 10.0, 12.0],
            "min_date": "2022-01-01",
            "max_date": "2022-01-06",
            "fetch_date": "2022-01-10T00:00:00Z",
            "row_count": 120,
        }, f)

    res = fetch(
        spec,
        cache_dir=tmp_path,
        float_index_path=snapshot_path,
        fetcher_engine=mock_engine,
    )

    assert res.status == FetchStatus.OVERSIZED
    assert res.data is None
    assert "Estimated profile count (120) exceeds the maximum limit (100)" in (res.error_message or "")
    assert "smaller region" in (res.suggestion or "")
    assert "shorter date window" in (res.suggestion or "")
    assert "shallower depth range" in (res.suggestion or "")
    assert mock_engine.call_count == 0


def test_coverage_full_applies_guard(tmp_path):
    """Proves full coverage applies the 100-profile guard."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Snapshot covering North Atlantic [-30, -28, 32, 34], Jan 1-10, 2022
    snapshot_path = tmp_path / "snap.parquet"
    mock_profiles = pd.DataFrame({
        "wmo": [6900000 + i for i in range(110)],
        "cycle_number": [1] * 110,
        "latitude": [33.0] * 110,
        "longitude": [-29.0] * 110,
        "date": [pd.Timestamp("2022-01-04")] * 110,
    })
    mock_profiles.to_parquet(snapshot_path, index=False)
    with open(tmp_path / "snap.json", "w", encoding="utf-8") as f:
        json.dump({
            "bbox": [-30.0, -28.0, 32.0, 34.0],
            "min_date": "2022-01-01",
            "max_date": "2022-01-10",
            "fetch_date": "2022-01-15T00:00:00Z",
            "row_count": 110,
        }, f)

    # Subtest: Fully covered query with 110 profiles (> 100 limit) -> Rejected!
    spec_over = QuerySpec(
        region=BoundingBox(lon_min=-29.5, lon_max=-28.5, lat_min=32.5, lat_max=33.5),
        date_range=DateRange(start=date(2022, 1, 2), end=date(2022, 1, 8)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    snap_res = count_profiles_in_snapshot(spec_over, snapshot_path=snapshot_path)
    assert snap_res.coverage == CoverageStatus.FULL
    assert snap_res.count == 110

    res_over = fetch(spec_over, cache_dir=tmp_path, float_index_path=snapshot_path, fetcher_engine=mock_engine)
    assert res_over.status == FetchStatus.OVERSIZED
    assert res_over.profile_count_verified is True
    assert res_over.coverage_status == CoverageStatus.FULL
    assert "Estimated profile count (110) exceeds the maximum limit (100)" in (res_over.error_message or "")
    assert mock_engine.call_count == 0


def test_coverage_uncovered_falls_back_to_cost_cap(tmp_path):
    """Proves uncovered query falls back to cost cap with profile_count_verified=False."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    # Snapshot covers North Atlantic [-30, -28, 32, 34]
    snapshot_path = tmp_path / "snap_na.parquet"
    mock_profiles = pd.DataFrame({
        "wmo": [6904128, 6901996],
        "cycle_number": [5, 5],
        "latitude": [33.0, 32.5],
        "longitude": [-29.0, -28.5],
        "date": [pd.Timestamp("2022-01-04"), pd.Timestamp("2022-01-06")],
    })
    mock_profiles.to_parquet(snapshot_path, index=False)
    with open(tmp_path / "snap_na.json", "w", encoding="utf-8") as f:
        json.dump({
            "bbox": [-30.0, -28.0, 32.0, 34.0],
            "min_date": "2022-01-01",
            "max_date": "2022-01-10",
            "fetch_date": "2022-01-15T00:00:00Z",
            "row_count": 2,
        }, f)

    # Query in Indian Ocean [60, 62, 10, 12]: completely disjoint from snapshot
    indian_ocean_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=62.0, lat_min=10.0, lat_max=12.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 5)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    snap_res = count_profiles_in_snapshot(indian_ocean_spec, snapshot_path=snapshot_path)
    assert snap_res.coverage == CoverageStatus.NOT_COVERED
    assert snap_res.count is None  # Does NOT treat count as 0

    res = fetch(
        indian_ocean_spec,
        cache_dir=tmp_path,
        float_index_path=snapshot_path,
        fetcher_engine=mock_engine,
    )
    # Passes because cost = 2 * 2 * 4 = 16 < 15,000; does not reject on profile count
    assert res.status == FetchStatus.SUCCESS
    assert res.profile_count_verified is False
    assert res.coverage_status == CoverageStatus.NOT_COVERED
    assert mock_engine.call_count == 1


def test_coverage_partial_falls_back_to_cost_cap(tmp_path):
    """Proves partially covered query falls back to cost cap with profile_count_verified=False."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    snapshot_path = tmp_path / "snap_partial.parquet"
    mock_profiles = pd.DataFrame({
        "wmo": [6904128],
        "cycle_number": [5],
        "latitude": [33.0],
        "longitude": [-29.0],
        "date": [pd.Timestamp("2022-01-04")],
    })
    mock_profiles.to_parquet(snapshot_path, index=False)
    with open(tmp_path / "snap_partial.json", "w", encoding="utf-8") as f:
        json.dump({
            "bbox": [-30.0, -28.0, 32.0, 34.0],
            "min_date": "2022-01-01",
            "max_date": "2022-01-10",
            "fetch_date": "2022-01-15T00:00:00Z",
            "row_count": 1,
        }, f)

    # Query bounding box spans [-32.0, -29.0, 32.0, 34.0]: partly inside, partly outside snapshot
    partial_spec = QuerySpec(
        region=BoundingBox(lon_min=-32.0, lon_max=-29.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 8)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    snap_res = count_profiles_in_snapshot(partial_spec, snapshot_path=snapshot_path)
    assert snap_res.coverage == CoverageStatus.PARTIAL

    res = fetch(
        partial_spec,
        cache_dir=tmp_path,
        float_index_path=snapshot_path,
        fetcher_engine=mock_engine,
    )
    assert res.status == FetchStatus.SUCCESS
    assert res.profile_count_verified is False
    assert res.coverage_status == CoverageStatus.PARTIAL
    assert mock_engine.call_count == 1


def test_request_extending_past_fetch_date_is_partial_coverage(tmp_path):
    """Proves request extending past snapshot fetch_date counts as partial coverage."""
    mock_engine = MagicMock(side_effect=lambda **kw: MockEngine(**kw))

    snapshot_path = tmp_path / "snap_dated.parquet"
    mock_profiles = pd.DataFrame({
        "wmo": [6904128],
        "cycle_number": [5],
        "latitude": [33.0],
        "longitude": [-29.0],
        "date": [pd.Timestamp("2022-01-04")],
    })
    mock_profiles.to_parquet(snapshot_path, index=False)
    # Snapshot was fetched on 2022-01-05
    with open(tmp_path / "snap_dated.json", "w", encoding="utf-8") as f:
        json.dump({
            "bbox": [-30.0, -28.0, 32.0, 34.0],
            "min_date": "2022-01-01",
            "max_date": "2022-01-10",
            "fetch_date": "2022-01-05T00:00:00Z",
            "row_count": 1,
        }, f)

    # Query date range extends to 2022-01-10 (past fetch_date 2022-01-05)
    extending_spec = QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    snap_res = count_profiles_in_snapshot(extending_spec, snapshot_path=snapshot_path)
    assert snap_res.coverage == CoverageStatus.PARTIAL

    res = fetch(
        extending_spec,
        cache_dir=tmp_path,
        float_index_path=snapshot_path,
        fetcher_engine=mock_engine,
    )
    assert res.status == FetchStatus.SUCCESS
    assert res.profile_count_verified is False
    assert res.coverage_status == CoverageStatus.PARTIAL
    assert mock_engine.call_count == 1


# --- Clearly marked live network test, skipped by default ---


@pytest.mark.skipif(
    not os.getenv("RUN_NETWORK_TESTS"),
    reason="Network test hitting remote ERDDAP skipped by default. Set RUN_NETWORK_TESTS=1 to run.",
)
def test_network_tiny_real_fetch(tmp_path, sample_spec):
    """Optional live network integration test verifying real ERDDAP server access and argopy pipeline."""
    res = fetch(sample_spec, cache_dir=tmp_path, force_refresh=True, timeout=60)
    assert res.status == FetchStatus.SUCCESS
    assert res.data is not None
    assert len(res.data) > 0
    assert not res.is_cached
    assert res.qc_report is not None
    assert res.metadata.source == "erddap"
    assert res.metadata.src == "erddap"
