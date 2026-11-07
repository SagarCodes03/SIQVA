"""Tests for large-query monthly chunking, caching, assembly, and limits (Q3b)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from siqva.card import build_card, generate_script, rerun
from siqva.chunking import (
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_TOTAL_ROWS,
    fetch_chunked,
    is_chunked_spec,
    split_date_range_into_months,
    validate_chunkable_spec,
)
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.qc import QCReport, audit_qc
from siqva.spec import DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable
from siqva.validator import OversizedRequestError, validate_spec


def test_split_date_range_single_month():
    dr = DateRange(start=date(2023, 3, 5), end=date(2023, 3, 25))
    chunks = split_date_range_into_months(dr)
    assert len(chunks) == 1
    chunk_dr, label = chunks[0]
    assert label == "2023-03"
    assert chunk_dr.start == date(2023, 3, 5)
    assert chunk_dr.end == date(2023, 3, 25)


def test_split_date_range_multi_month_across_year():
    dr = DateRange(start=date(2022, 11, 15), end=date(2023, 2, 10))
    chunks = split_date_range_into_months(dr)
    assert len(chunks) == 4
    labels = [label for _, label in chunks]
    assert labels == ["2022-11", "2022-12", "2023-01", "2023-02"]

    assert chunks[0][0].start == date(2022, 11, 15)
    assert chunks[0][0].end == date(2022, 11, 30)

    assert chunks[1][0].start == date(2022, 12, 1)
    assert chunks[1][0].end == date(2022, 12, 31)

    assert chunks[2][0].start == date(2023, 1, 1)
    assert chunks[2][0].end == date(2023, 1, 31)

    assert chunks[3][0].start == date(2023, 2, 1)
    assert chunks[3][0].end == date(2023, 2, 10)


def test_split_date_range_leap_year_february():
    dr = DateRange(start=date(2024, 2, 1), end=date(2024, 2, 29))
    chunks = split_date_range_into_months(dr)
    assert len(chunks) == 1
    assert chunks[0][1] == "2024-02"
    assert chunks[0][0].end == date(2024, 2, 29)


def test_oversized_query_exceeding_max_chunks_is_rejected():
    # 26 months (Jan 2022 to Feb 2024) > default 24
    spec = QuerySpec(
        region=[60.0, 70.0, 10.0, 20.0],  # area = 100 sq deg
        date_range=["2022-01-01", "2024-02-28"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    with pytest.raises(OversizedRequestError, match="exceeds the limit of 24"):
        validate_chunkable_spec(spec, max_chunks=24)


def test_single_month_exceeding_cost_cap_cannot_be_chunked():
    # Giant region: area = 50 * 50 = 2500 sq deg
    # For 1 month (30 days): 2500 * 30 = 75,000 > 15,000
    spec = QuerySpec(
        region=[20.0, 70.0, -10.0, 40.0],
        date_range=["2022-01-01", "2022-06-30"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    with pytest.raises(OversizedRequestError) as exc_info:
        validate_chunkable_spec(spec, max_request_size=15000.0)
    assert "exceeds the allowable request size" in str(exc_info.value)
    assert "Please narrow your query" in exc_info.value.suggestion


def test_chunkable_spec_passes_validation_when_allowed():
    # Arabian Sea: 25 * 15 = 375 sq deg.
    # 1 year (365 days): 375 * 365 = 136,875 > 15,000.
    # But 1 month (~30 days): 375 * 31 = 11,625 <= 15,000.
    # 12 months <= 24 limit.
    spec = QuerySpec(
        region=[50.0, 75.0, 10.0, 25.0],
        date_range=["2022-01-01", "2022-12-31"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    assert is_chunked_spec(spec, max_request_size=15000.0) is True

    # Standard validate_spec without chunking raises OversizedRequestError
    with pytest.raises(OversizedRequestError):
        validate_spec(spec, max_request_size=15000.0, allow_chunking=False)

    # validate_spec with allow_chunking=True passes cleanly
    validate_spec(spec, max_request_size=15000.0, allow_chunking=True)


def test_fetch_chunked_success_and_deduplication():
    # Spec spanning 2 months: 2023-01 to 2023-02
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-02-28"],
        variables=["TEMP", "PSAL"],
        intent=Intent.PROFILE,
    )

    df_month1 = pd.DataFrame({
        "PLATFORM_NUMBER": [69001, 69001, 69002],
        "CYCLE_NUMBER": [1, 1, 1],
        "PRES": [10.0, 20.0, 10.0],
        "TIME": pd.to_datetime(["2023-01-05", "2023-01-05", "2023-01-15"]),
        "TEMP": [25.0, 24.5, 26.0],
        "PSAL": [35.0, 35.1, 35.2],
        "TEMP_QC": [1, 1, 1],
        "PSAL_QC": [1, 1, 1],
    })

    # df_month2 contains an overlapping record (boundary profile) plus a new profile
    df_month2 = pd.DataFrame({
        "PLATFORM_NUMBER": [69002, 69003],
        "CYCLE_NUMBER": [1, 2],
        "PRES": [10.0, 15.0],
        "TIME": pd.to_datetime(["2023-01-15", "2023-02-10"]),
        "TEMP": [26.0, 23.0],
        "PSAL": [35.2, 34.8],
        "TEMP_QC": [1, 1],
        "PSAL_QC": [1, 1],
    })

    call_count = 0

    def mock_fetcher(chunk_spec, **kwargs):
        nonlocal call_count
        call_count += 1
        label = chunk_spec.date_range.start.strftime("%Y-%m")
        df = df_month1 if label == "2023-01" else df_month2
        return FetchResult(
            status=FetchStatus.SUCCESS,
            data=df.copy(),
            is_cached=True,
            cache_key=chunk_spec.fetch_key(),
            metadata=FetchMetadata(
                src="erddap",
                source="erddap",
                argopy_version="1.5.0",
                xarray_version="2026.9.0",
                fetch_timestamp="2026-11-07T00:00:00Z",
                row_count=len(df),
                profile_count=2,
                data_hash="dummy_hash",
                fetch_key=chunk_spec.fetch_key(),
            ),
            qc_report=audit_qc(df, chunk_spec.variables, chunk_spec.mode),
        )

    res = fetch_chunked(spec, fetcher_fn=mock_fetcher)

    assert res.status == FetchStatus.SUCCESS
    assert call_count == 2
    # Combined df had 3 rows (month1) + 2 rows (month2) = 5 rows, but 1 was duplicate
    assert len(res.data) == 4
    # Profiles: (69001, 1), (69002, 1), (69003, 2) -> exactly 3 unique profiles
    assert res.profile_count == 3
    assert res.is_cached is True
    assert res.metadata is not None


def test_fetch_chunked_failure_reports_failed_month():
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-03-31"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )

    def failing_fetcher(chunk_spec, **kwargs):
        label = chunk_spec.date_range.start.strftime("%Y-%m")
        if label == "2023-02":
            return FetchResult(
                status=FetchStatus.TIMEOUT,
                data=None,
                error_message="Remote ERDDAP timed out after 30s",
            )
        return FetchResult(
            status=FetchStatus.SUCCESS,
            data=pd.DataFrame({"TEMP": [25.0]}),
            is_cached=True,
        )

    res = fetch_chunked(spec, fetcher_fn=failing_fetcher)
    assert res.status == FetchStatus.TIMEOUT
    assert "Failed while fetching monthly chunk 2023-02" in res.error_message
    assert "Any completed chunks (1/3) remain cached" in res.error_message


def test_fetch_chunked_enforces_row_limit():
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-02-28"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )

    def large_df_fetcher(chunk_spec, **kwargs):
        # 100 rows per chunk
        return FetchResult(
            status=FetchStatus.SUCCESS,
            data=pd.DataFrame({"TEMP": [25.0] * 100}),
            is_cached=True,
        )

    # Set row limit to 150 rows -> second chunk pushes it to 200 > 150
    res = fetch_chunked(spec, fetcher_fn=large_df_fetcher, max_total_rows=150)
    assert res.status == FetchStatus.OVERSIZED
    assert "Combined row count (200) exceeded the maximum allowable limit of 150" in res.error_message


def test_query_card_records_chunks_and_generates_chunked_script():
    spec = QuerySpec(
        region=[50.0, 75.0, 10.0, 25.0],
        date_range=["2022-01-01", "2022-03-31"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=pd.DataFrame({
            "PLATFORM_NUMBER": [69001],
            "CYCLE_NUMBER": [1],
            "PRES": [10.0],
            "TIME": pd.to_datetime(["2022-01-10"]),
            "TEMP": [25.0],
            "TEMP_QC": [1],
        }),
        is_cached=False,
    )

    card = build_card(spec, fetch_res)
    assert card.chunks is not None
    assert card.chunks == ["2022-01", "2022-02", "2022-03"]

    script = generate_script(card)
    assert "Chunked Fetch: 3 monthly chunks" in script
    assert "for start_d, end_d in chunks:" in script
    assert "pd.concat(dfs, ignore_index=True)" in script


def test_rerun_executes_chunked_fetcher():
    spec = QuerySpec(
        region=[50.0, 75.0, 10.0, 25.0],
        date_range=["2022-01-01", "2022-03-31"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    df = pd.DataFrame({
        "PLATFORM_NUMBER": [69001],
        "CYCLE_NUMBER": [1],
        "PRES": [10.0],
        "TIME": pd.to_datetime(["2022-01-10"]),
        "TEMP": [25.0],
        "TEMP_QC": [1],
    })
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=False,
    )
    card = build_card(spec, fetch_res)

    mock_fn = MagicMock(return_value=fetch_res)
    diff = rerun(card, fetcher_fn=mock_fn)
    assert diff.is_same is True
    assert diff.summary.startswith("Data identical")
