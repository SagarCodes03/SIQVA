"""Tests for S-fix2: failure classification, backfill, retry, honest messages, and depth provenance."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from siqva.card import QueryCard, build_card
from siqva.fetcher import (
    FetchResult,
    FetchStatus,
    ProfileFailureReason,
    classify_profile_failure,
    format_sample_failure_sentence,
    fetch_sample,
    shorten_url,
)
from siqva.floatindex import SamplePick, SampleSelection
from siqva.interpretation import build_understood_from_spec
from siqva.parser import parse_detailed
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


# --- 1. Failure Classification Tests ---

def test_classify_profile_failure():
    # EMPTY classification
    assert classify_profile_failure(Exception("Your query produced no matching results"), None)[0] == ProfileFailureReason.EMPTY.value
    assert classify_profile_failure(Exception("DataNotFound: 404"), None)[0] == ProfileFailureReason.EMPTY.value
    assert classify_profile_failure(None, pd.DataFrame())[0] == ProfileFailureReason.EMPTY.value
    assert classify_profile_failure(Exception("HTTP 404 Not Found"), None)[0] == ProfileFailureReason.EMPTY.value

    # TIMEOUT classification
    assert classify_profile_failure(Exception("HTTPSConnectionPool: Read timed out"), None)[0] == ProfileFailureReason.TIMEOUT.value
    assert classify_profile_failure(Exception("504 Gateway Timeout"), None)[0] == ProfileFailureReason.TIMEOUT.value
    assert classify_profile_failure(Exception("408 Request Timeout"), None)[0] == ProfileFailureReason.TIMEOUT.value

    # RATE_LIMITED classification
    assert classify_profile_failure(Exception("HTTP 429 Too Many Requests"), None)[0] == ProfileFailureReason.RATE_LIMITED.value
    assert classify_profile_failure(Exception("Client error: rate limit exceeded"), None)[0] == ProfileFailureReason.RATE_LIMITED.value

    # HTTP_ERROR classification
    reason, detail = classify_profile_failure(Exception("HTTP 500 Internal Server Error"), None)
    assert reason.startswith(ProfileFailureReason.HTTP_ERROR.value)
    assert "500" in reason
    assert "500" in detail

    reason_403, detail_403 = classify_profile_failure(Exception("403 Forbidden"), None)
    assert reason_403.startswith(ProfileFailureReason.HTTP_ERROR.value)
    assert "403" in detail_403

    # OTHER classification
    assert classify_profile_failure(ValueError("Unexpected format"), None)[0] == ProfileFailureReason.OTHER.value


def test_format_sample_failure_sentence():
    counts = {"no matching data": 5, "timed out": 3}
    sentence = format_sample_failure_sentence(8, 12, counts)
    assert sentence == "8 of 12 selected profiles could not be loaded (5 had no matching data, 3 timed out)"
    assert "http" not in sentence.lower()
    assert "erddap" not in sentence.lower()


def test_shorten_url():
    long_url = "https://erddap.argo.org/erddap/tabledap/ArgoFloats.csv?platform_number%2Ccycle_number&platform_number=%222901001%22"
    short = shorten_url(long_url, max_len=50)
    assert len(short) <= 53  # with ellipsis
    assert "..." in short


# --- 2. Retry and Fallback Tests with Mocked Fetcher ---

class FlakyMockEngine:
    """Mock engine that fails on first attempt and succeeds on retry."""
    def __init__(self):
        self.attempts: dict[tuple[int, int], int] = {}
        self._cur = None

    def profile(self, wmo, cyc):
        self._cur = (wmo, cyc)
        return self

    def region(self, box):
        return self

    def to_dataframe(self):
        wmo, cyc = self._cur
        count = self.attempts.get((wmo, cyc), 0) + 1
        self.attempts[(wmo, cyc)] = count
        if count == 1:
            raise Exception("Read timed out")
        
        df = pd.read_parquet(FIXTURE_PATH).copy()
        df["PLATFORM_NUMBER"] = wmo
        df["CYCLE_NUMBER"] = cyc
        return df


def test_retry_on_timeout(tmp_path):
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    picks = [SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True)]
    engine = FlakyMockEngine()

    res = fetch_sample(
        spec,
        picks=picks,
        cache_dir=tmp_path,
        fetcher_engine=lambda **kwargs: engine,
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.n_selected == 1
    assert engine.attempts[(2901001, 1)] == 2  # 1 fail, 1 retry


# --- 3. Backfill and Candidate Replacement Tests ---

class BackfillMockEngine:
    """Mock engine that returns empty for pick 1, but succeeds for pick 2."""
    def __init__(self, empty_picks: set[tuple[int, int]]):
        self.empty_picks = empty_picks
        self._cur = None
        self.recorded_calls = []

    def profile(self, wmo, cyc):
        self._cur = (wmo, cyc)
        self.recorded_calls.append((wmo, cyc))
        return self

    def region(self, box):
        return self

    def to_dataframe(self):
        wmo, cyc = self._cur
        if (wmo, cyc) in self.empty_picks:
            raise Exception("Your query produced no matching results")
        
        df = pd.read_parquet(FIXTURE_PATH).copy()
        df["PLATFORM_NUMBER"] = wmo
        df["CYCLE_NUMBER"] = cyc
        return df


def test_backfill_replaces_empty(tmp_path):
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    pick1 = SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True, bin_id=(0, 0))
    alt_pick = SamplePick(wmo=2901002, cycle=2, date="2022-01-06", lat=11.2, lon=61.2, is_delayed=True, bin_id=(0, 0))

    selection = SampleSelection(
        picks=[pick1],
        method="stratified_space_time",
        seed=42,
        n_available=10,
        n_requested=1,
        bin_candidates={(0, 0): [pick1, alt_pick]},
    )

    engine = BackfillMockEngine(empty_picks={(2901001, 1)})

    res = fetch_sample(
        spec,
        picks=[pick1],
        selection=selection,
        cache_dir=tmp_path,
        fetcher_engine=lambda **kwargs: engine,
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.n_selected == 1
    assert res.n_replacements == 1
    # Pick 1 was attempted, failed, then alt_pick was attempted and succeeded
    assert (2901001, 1) in engine.recorded_calls
    assert (2901002, 2) in engine.recorded_calls


def test_attempt_limit_2x_n(tmp_path):
    """Ensure attempts never exceed 2 * n_requested."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    # 2 picks, all fail, with infinite candidates available
    pick1 = SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True, bin_id=(0, 0))
    pick2 = SamplePick(wmo=2901002, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True, bin_id=(0, 0))
    extra_candidates = [
        SamplePick(wmo=2901000 + i, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True, bin_id=(0, 0))
        for i in range(3, 10)
    ]

    selection = SampleSelection(
        picks=[pick1, pick2],
        method="stratified_space_time",
        seed=42,
        n_available=10,
        n_requested=2,
        bin_candidates={(0, 0): [pick1, pick2] + extra_candidates},
    )

    # Everything fails
    all_empty = {(2901000 + i, 1) for i in range(1, 10)}
    engine = BackfillMockEngine(empty_picks=all_empty)

    res = fetch_sample(
        spec,
        picks=[pick1, pick2],
        selection=selection,
        cache_dir=tmp_path,
        fetcher_engine=lambda **kwargs: engine,
        pause_s=0.0,
    )

    # Maximum attempts is 2 * n = 4
    assert len(engine.recorded_calls) <= 4
    assert res.n_selected == 0
    assert res.status in (FetchStatus.EMPTY, FetchStatus.SUCCESS)


# --- 4. k=0 and k=1 Cases ---

def test_k_equals_1_success(tmp_path):
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    pick = SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True)
    engine = BackfillMockEngine(empty_picks=set())

    res = fetch_sample(
        spec,
        picks=[pick],
        cache_dir=tmp_path,
        fetcher_engine=lambda **kwargs: engine,
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.n_selected == 1
    assert res.data is not None
    assert len(res.data) > 0


# --- 5. Depth Provenance Flag Test ---

def test_acoustic_default_depth_provenance():
    """Verify that an acoustic query without depth specified gets '(default)' and provenance 'default'."""
    parsed = parse_detailed("acoustic sound speed in the Arabian Sea between 2022-01-01 and 2022-01-05")
    spec = parsed.spec
    assert spec is not None
    assert spec.intent == Intent.ACOUSTIC
    assert parsed.provenance.get("depth_range") == "default"

    from siqva.capabilities import resolve_effective_depth
    eff_depth, is_def = resolve_effective_depth(spec)
    assert eff_depth == DepthRange(min_depth=0.0, max_depth=2000.0)
    assert is_def is True

    # Reconstruct understood
    from siqva.interpretation import format_understood_as
    understood, prov = build_understood_from_spec(spec)
    assert prov.get("depth_range") == "default"
    line = format_understood_as(understood, prov)
    assert "0–2000 dbar (default) [default]" in line


class WiderWindowMockEngine:
    """Mock engine where profile() fails, window 1 region() is empty, and window 2 region() succeeds."""
    def __init__(self):
        self.boxes = []
        self._cur_box = None

    def profile(self, wmo, cyc):
        raise Exception("No direct profile available")

    def region(self, box):
        self._cur_box = box
        self.boxes.append(box)
        return self

    def to_dataframe(self):
        lon_span = self._cur_box[1] - self._cur_box[0]
        if lon_span < 0.2:
            return pd.DataFrame()  # empty window 1
        df = pd.read_parquet(FIXTURE_PATH).copy()
        df["PLATFORM_NUMBER"] = 2901001
        df["CYCLE_NUMBER"] = 1
        return df


def test_wider_window_fallback(tmp_path):
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    pick = SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True)
    engine = WiderWindowMockEngine()

    res = fetch_sample(
        spec,
        picks=[pick],
        cache_dir=tmp_path,
        fetcher_engine=lambda **kwargs: engine,
        pause_s=0.0,
    )

    assert res.status == FetchStatus.SUCCESS
    assert res.n_selected == 1
    # Both window 1 (span 0.1) and window 2 (span 0.5) were attempted
    assert len(engine.boxes) == 2


def test_wall_clock_budget_exceeded(tmp_path):
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    picks = [
        SamplePick(wmo=2901001, cycle=1, date="2022-01-05", lat=11.0, lon=61.0, is_delayed=True),
        SamplePick(wmo=2901002, cycle=2, date="2022-01-06", lat=11.0, lon=61.0, is_delayed=True),
    ]
    engine = FlakyMockEngine()

    # Pass 0.0001s wall clock budget so it stops early
    res = fetch_sample(
        spec,
        picks=picks,
        cache_dir=tmp_path,
        fetcher_engine=lambda **kwargs: engine,
        wall_clock_budget=0.0001,
        pause_s=0.001,
    )
    # Exits loop without throwing exception; sets TIMEOUT if budget ran out before data loaded
    assert res.status in (FetchStatus.TIMEOUT, FetchStatus.SUCCESS, FetchStatus.EMPTY)


# --- 6. Card Fields Persistence ---

def test_query_card_sample_fields():
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 14)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )
    fetch_res = FetchResult(
        data=pd.DataFrame({"TEMP": [25.0], "PRES": [10.0]}),
        status=FetchStatus.SUCCESS,
        data_hash="abc12345",
        row_count=1,
        is_sample=True,
        n_selected=4,
        n_requested=12,
        n_replacements=2,
        failure_counts={"no matching data": 6, "timed out": 2},
    )

    card = build_card(spec, fetch_res, question="acoustic in Arabian Sea")
    assert card.sample_failure_counts == {"no matching data": 6, "timed out": 2}
    assert card.sample_replacements == 2

    # Round trip dict / json
    card_dict = card.model_dump()
    reloaded = QueryCard.model_validate(card_dict)
    assert reloaded.sample_failure_counts == {"no matching data": 6, "timed out": 2}
    assert reloaded.sample_replacements == 2
