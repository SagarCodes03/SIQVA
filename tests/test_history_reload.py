"""Tests for history card reload, plot restoration, and session privacy (Q11)."""

import os
from pathlib import Path
import pandas as pd
import pytest

from siqva.card import (
    build_card,
    is_history_shared,
    list_cards,
    load_card,
    restore_card_result,
    save_card,
)
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.pipeline import PipelineStatus
from siqva.spec import DataMode, DepthRange, Intent, QuerySpec, Variable


@pytest.fixture
def sample_card_and_parquet(tmp_path: Path):
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2022-01-01", "2022-01-10"],
        variables=["TEMP", "PSAL"],
        intent=Intent.PROFILE,
    )
    df = pd.DataFrame({
        "PLATFORM_NUMBER": [69001, 69001],
        "CYCLE_NUMBER": [1, 1],
        "PRES": [10.0, 50.0],
        "TEMP": [25.0, 24.0],
        "PSAL": [35.0, 35.2],
        "TIME": pd.to_datetime(["2022-01-05", "2022-01-05"]),
        "LATITUDE": [12.0, 12.0],
        "LONGITUDE": [62.0, 62.0],
    })
    parquet_path = tmp_path / f"{spec.fetch_key()}.parquet"
    df.to_parquet(parquet_path)

    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=True,
        cache_key=spec.fetch_key(),
        metadata=FetchMetadata(
            src="erddap",
            source="erddap",
            argopy_version="1.5.0",
            xarray_version="2026.9.0",
            fetch_timestamp="2026-11-07T00:00:00Z",
            row_count=2,
            profile_count=1,
            data_hash="dummy_hash",
            fetch_key=spec.fetch_key(),
        ),
    )
    card = build_card(spec, fetch_res, question="sample query", session_id="user_sess_1")
    return card, tmp_path


def test_restore_card_result_with_cached_parquet(sample_card_and_parquet):
    card, cache_dir = sample_card_and_parquet
    res = restore_card_result(card, cache_dir=cache_dir)

    assert res.status == PipelineStatus.SUCCESS
    assert res.fetch_result is not None
    assert res.fetch_result.data is not None
    assert len(res.fetch_result.data) == 2
    assert "map" in res.figures
    assert "profile" in res.figures
    assert res.analysis is not None
    assert res.card.card_id == card.card_id


def test_restore_card_result_when_parquet_missing(tmp_path: Path):
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2022-01-01", "2022-01-10"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    fetch_res = FetchResult(status=FetchStatus.SUCCESS, is_cached=True)
    card = build_card(spec, fetch_res)

    empty_cache = tmp_path / "empty_cache"
    empty_cache.mkdir()

    res = restore_card_result(card, cache_dir=empty_cache)
    assert res.status == PipelineStatus.SUCCESS
    assert res.fetch_result is None
    assert "Cached data not on disk" in res.warning
    assert "RE-RUN FETCH" in res.warning


def test_session_privacy_isolation(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test_cards.sqlite"

    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2022-01-01", "2022-01-10"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    fetch_res = FetchResult(status=FetchStatus.SUCCESS)

    card_sess_a = build_card(spec, fetch_res, session_id="session_A")
    save_card(card_sess_a, db_path=db_file)

    # 1. Default: history is shared
    monkeypatch.delenv("SIQVA_SHARED_HISTORY", raising=False)
    assert is_history_shared() is True
    all_cards = list_cards(session_id="session_B", db_path=db_file)
    assert len(all_cards) == 1

    # 2. Private: history is NOT shared (SIQVA_SHARED_HISTORY=0)
    monkeypatch.setenv("SIQVA_SHARED_HISTORY", "0")
    assert is_history_shared() is False

    # session_B cannot see session_A's card in list
    b_cards = list_cards(session_id="session_B", db_path=db_file)
    assert len(b_cards) == 0

    # session_A CAN see its own card
    a_cards = list_cards(session_id="session_A", db_path=db_file)
    assert len(a_cards) == 1

    # Direct load_card access control
    loaded_by_b = load_card(card_sess_a.card_id, session_id="session_B", db_path=db_file)
    assert loaded_by_b is None

    loaded_by_a = load_card(card_sess_a.card_id, session_id="session_A", db_path=db_file)
    assert loaded_by_a is not None
    assert loaded_by_a.card_id == card_sess_a.card_id
