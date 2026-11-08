"""Large-query chunking: calendar-month query splitting, caching, assembly, and limits."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

import argopy
import pandas as pd
import xarray as xr

from .qc import QCReport, audit_qc
from .spec import DateRange, DepthRange, QuerySpec
from .validator import (
    DEFAULT_MAX_REQUEST_SIZE,
    OversizedRequestError,
    format_oversized_suggestion,
    is_size_guardrail_enabled,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHUNKS: int = 24
DEFAULT_MAX_TOTAL_ROWS: int = 3_000_000


def get_max_chunks() -> int:
    """Return maximum allowable monthly chunks from environment or default."""
    val = os.getenv("SIQVA_MAX_CHUNKS")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MAX_CHUNKS


def get_max_total_rows() -> int:
    """Return maximum allowable combined rows from environment or default."""
    val = os.getenv("SIQVA_MAX_TOTAL_ROWS")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MAX_TOTAL_ROWS


def split_date_range_into_months(date_range: DateRange) -> list[tuple[DateRange, str]]:
    """Split a DateRange into contiguous calendar-month segments.

    Returns:
        List of (DateRange, label) tuples where label is 'YYYY-MM'.
    """
    start = date_range.start
    end = date_range.end

    if start > end:
        return []

    chunks: list[tuple[DateRange, str]] = []
    curr_year = start.year
    curr_month = start.month

    while (curr_year < end.year) or (curr_year == end.year and curr_month <= end.month):
        month_label = f"{curr_year:04d}-{curr_month:02d}"
        _, last_day = calendar.monthrange(curr_year, curr_month)

        chunk_start = start if (curr_year == start.year and curr_month == start.month) else date(curr_year, curr_month, 1)
        chunk_end = end if (curr_year == end.year and curr_month == end.month) else date(curr_year, curr_month, last_day)

        chunks.append((DateRange(start=chunk_start, end=chunk_end), month_label))

        if curr_month == 12:
            curr_month = 1
            curr_year += 1
        else:
            curr_month += 1

    return chunks


def compute_spec_cost(spec: QuerySpec) -> tuple[float, float, int, float]:
    """Calculate geographic area, duration, depth factor, and total cost units for a spec.

    Returns:
        (area, days, depth_span, cost)
    """
    bbox = spec.region
    area = (bbox.lon_max - bbox.lon_min) * (bbox.lat_max - bbox.lat_min)
    days = max(1, (spec.date_range.end - spec.date_range.start).days)
    depth = spec.depth_range or DepthRange(min_depth=0.0, max_depth=500.0)
    depth_span = max(1.0, depth.max_depth - depth.min_depth)
    depth_factor = depth_span / 500.0
    cost = area * days * depth_factor
    return area, days, depth_span, cost


def is_chunked_spec(spec: QuerySpec, max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE) -> bool:
    """Check whether a query spec exceeds the single-request cost cap and has multiple calendar months."""
    chunks = split_date_range_into_months(spec.date_range)
    if len(chunks) <= 1:
        return False
    if max_request_size is None or not is_size_guardrail_enabled():
        return True
    _, _, _, cost = compute_spec_cost(spec)
    if cost <= max_request_size:
        return False
    return True


def validate_chunkable_spec(
    spec: QuerySpec,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
    max_chunks: Optional[int] = None,
) -> bool:
    """Validate whether an oversized spec can be satisfied via monthly chunking.

    Raises:
        OversizedRequestError: If any individual month exceeds max_request_size, or
                               if total required chunks exceeds max_chunks.
    Returns:
        True if the query can be split into valid chunks.
    """
    chunks = split_date_range_into_months(spec.date_range)
    if not chunks:
        return False

    if is_size_guardrail_enabled() and max_request_size is not None:
        if max_chunks is None:
            max_chunks = get_max_chunks()
        if len(chunks) > max_chunks:
            raise OversizedRequestError(
                message=(
                    f"Requested date range requires {len(chunks)} monthly chunks, which exceeds the limit "
                    f"of {max_chunks}. Please narrow your date range to at most {max_chunks} months."
                ),
                area=0.0,
                days=max(1, (spec.date_range.end - spec.date_range.start).days),
                size=float(len(chunks)),
                max_size=float(max_chunks),
                suggestion=f"Please narrow your date range to at most {max_chunks} months.",
                depth_span=0.0,
            )

    area, _, depth_span, _ = compute_spec_cost(spec)
    depth_factor = depth_span / 500.0
    depth = spec.depth_range or DepthRange(min_depth=0.0, max_depth=500.0)

    # Check whether any individual month exceeds the cap (if size guardrail is active)
    if is_size_guardrail_enabled() and max_request_size is not None:
        for chunk_range, chunk_label in chunks:
            chunk_days = max(1, (chunk_range.end - chunk_range.start).days)
            chunk_cost = area * chunk_days * depth_factor
            if chunk_cost > max_request_size:
                from .gazetteer import KNOWN_REGIONS

                region_name = next(
                    (name for name, b in KNOWN_REGIONS.items() if b == spec.region),
                    None,
                )
                suggestion = format_oversized_suggestion(
                    area=area,
                    days=chunk_days,
                    depth_span=depth_span,
                    cost=chunk_cost,
                    max_request_size=max_request_size,
                    region_name=region_name,
                    min_depth=depth.min_depth,
                    max_depth=depth.max_depth,
                )
                raise OversizedRequestError(
                    message=(
                        f"Monthly chunk '{chunk_label}' exceeds the allowable request size "
                        f"({chunk_cost:.0f} > {max_request_size:.0f} cost units). {suggestion}"
                    ),
                    area=area,
                    days=chunk_days,
                    size=chunk_cost,
                    max_size=max_request_size,
                    suggestion=suggestion,
                    depth_span=depth_span,
                )

    return True


def fetch_chunked(
    spec: QuerySpec,
    cache_dir: Optional[Path | str] = None,
    force_refresh: bool = False,
    fetcher_fn: Any = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    max_chunks: Optional[int] = None,
    max_total_rows: Optional[int] = None,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
    **fetch_kwargs: Any,
) -> Any:
    """Fetch a large multi-month query by decomposing it into calendar-month requests.

    Each month is fetched via standard fetch(), taking full advantage of the Parquet cache.
    Results are concatenated and deduplicated across chunk boundaries.
    """
    from .fetcher import (
        FetchMetadata,
        FetchResult,
        FetchStatus,
        compute_canonical_data_hash,
        count_unique_profiles,
        fetch,
    )

    if fetcher_fn is None:
        fetcher_fn = fetch

    if max_total_rows is None:
        max_total_rows = get_max_total_rows()

    depth = spec.depth_range or DepthRange(min_depth=0.0, max_depth=500.0)
    chunks = split_date_range_into_months(spec.date_range)

    if is_size_guardrail_enabled() and max_request_size is not None:
        if max_chunks is None:
            max_chunks = get_max_chunks()
        if len(chunks) > max_chunks:
            return FetchResult(
                status=FetchStatus.OVERSIZED,
                data=None,
                is_cached=False,
                cache_key=spec.fetch_key(),
                error_message=(
                    f"Requested date range requires {len(chunks)} monthly chunks, which exceeds the limit "
                    f"of {max_chunks}. Please narrow your date range to at most {max_chunks} months."
                ),
                suggestion=f"Please narrow your date range to at most {max_chunks} months.",
                effective_depth_range=depth,
            )

    chunk_dfs: list[pd.DataFrame] = []
    cached_chunk_count: int = 0
    total_chunks = len(chunks)

    for idx, (chunk_range, chunk_label) in enumerate(chunks):
        if progress_callback is not None:
            try:
                progress_callback(idx + 1, total_chunks, chunk_label)
            except Exception:
                pass

        chunk_spec = spec.model_copy(update={"date_range": chunk_range})
        res: FetchResult = fetcher_fn(
            chunk_spec,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
            max_request_size=max_request_size,
            **fetch_kwargs,
        )

        if res.status in (FetchStatus.ERROR, FetchStatus.TIMEOUT):
            return FetchResult(
                status=res.status,
                data=None,
                is_cached=False,
                cache_key=spec.fetch_key(),
                error_message=(
                    f"Failed while fetching monthly chunk {chunk_label} ({chunk_range.start} to {chunk_range.end}): "
                    f"{res.error_message or 'Unknown fetch error'}. "
                    f"Any completed chunks ({idx}/{total_chunks}) remain cached for future queries."
                ),
                suggestion="You can retry the query or choose a narrower date range.",
                effective_depth_range=depth,
            )

        if res.status == FetchStatus.OVERSIZED:
            return FetchResult(
                status=FetchStatus.OVERSIZED,
                data=None,
                is_cached=False,
                cache_key=spec.fetch_key(),
                error_message=f"Chunk {chunk_label} exceeds allowable profile or size limits: {res.error_message}",
                suggestion=res.suggestion,
                effective_depth_range=depth,
            )

        if res.is_cached:
            cached_chunk_count += 1

        if res.data is not None and len(res.data) > 0:
            chunk_dfs.append(res.data)

        # Enforce cumulative row limit (only when size guardrails are enabled)
        current_rows = sum(len(df) for df in chunk_dfs)
        if (
            is_size_guardrail_enabled()
            and max_request_size is not None
            and max_total_rows is not None
            and current_rows > max_total_rows
        ):
            return FetchResult(
                status=FetchStatus.OVERSIZED,
                data=None,
                is_cached=False,
                cache_key=spec.fetch_key(),
                error_message=(
                    f"Combined row count ({current_rows:,}) exceeded the maximum allowable limit of "
                    f"{max_total_rows:,} rows across monthly chunks."
                ),
                suggestion="Please narrow your date range or choose a smaller geographic region.",
                effective_depth_range=depth,
            )

    if not chunk_dfs:
        return FetchResult(
            status=FetchStatus.EMPTY,
            data=None,
            is_cached=(cached_chunk_count == total_chunks),
            cache_key=spec.fetch_key(),
            error_message="No Argo observations were found matching the query constraints across all requested months.",
            suggestion="Try expanding the geographic region or selecting a different year.",
            effective_depth_range=depth,
            profile_count=0,
            profile_count_verified=True,
        )

    # Combine and deduplicate across chunks
    combined_df = pd.concat(chunk_dfs, ignore_index=True)
    dedup_cols = [c for c in ["PLATFORM_NUMBER", "CYCLE_NUMBER", "PRES", "TIME"] if c in combined_df.columns]
    if dedup_cols:
        combined_df = combined_df.drop_duplicates(subset=dedup_cols).reset_index(drop=True)

    r_count = len(combined_df)
    p_count = count_unique_profiles(combined_df)
    d_hash = compute_canonical_data_hash(combined_df)
    qc_rep = audit_qc(combined_df, spec.variables, spec.mode)

    metadata = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version=str(argopy.__version__),
        xarray_version=str(xr.__version__),
        fetch_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        row_count=r_count,
        profile_count=p_count,
        data_hash=d_hash,
        fetch_key=spec.fetch_key(),
    )

    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=combined_df,
        is_cached=(cached_chunk_count == total_chunks),
        cache_key=spec.fetch_key(),
        metadata=metadata,
        qc_report=qc_rep,
        effective_depth_range=depth,
        profile_count=p_count,
        profile_count_verified=False,
    )
