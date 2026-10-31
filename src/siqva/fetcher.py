"""Argo data fetcher wrapping argopy with explicit mode control, Parquet caching, and sidecar metadata."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import argopy
import pandas as pd
import xarray as xr
from pydantic import BaseModel, ConfigDict, Field

from .qc import QCReport, audit_qc
from .spec import DataMode, DepthRange, QuerySpec
from .validator import DEFAULT_MAX_REQUEST_SIZE, OversizedRequestError, SpecValidationError, validate_spec

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("cache")
DEFAULT_CACHE_EXPIRY_DAYS = 7
DEFAULT_RESEARCH_CACHE_EXPIRY_DAYS = 90

DEFAULT_FLOAT_INDEX_PATH = Path("data/float_index.parquet")

# Default maximum allowable profiles before a request is rejected as oversized.
# Provisional value based on limited measurements (single region and period); should be revisited.
DEFAULT_MAX_PROFILE_COUNT: int = 100


class FetchStatus(str, Enum):
    """Execution status for Argo data fetch requests."""

    SUCCESS = "success"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    OVERSIZED = "oversized"
    ERROR = "error"


class CoverageStatus(str, Enum):
    """Geographic and temporal coverage status of a query relative to the float index snapshot."""

    FULL = "full"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"


class SnapshotProfileResult(BaseModel):
    """Result of querying local float index snapshot for profile count and coverage."""

    model_config = ConfigDict(frozen=True)

    count: Optional[int] = None
    coverage: CoverageStatus = CoverageStatus.NOT_COVERED
    details: Optional[str] = None

    @property
    def is_fully_covered(self) -> bool:
        return self.coverage == CoverageStatus.FULL

    @property
    def is_partly_covered(self) -> bool:
        return self.coverage == CoverageStatus.PARTIAL

    @property
    def is_uncovered(self) -> bool:
        return self.coverage == CoverageStatus.NOT_COVERED


class FetchMetadata(BaseModel):
    """Sidecar metadata describing the provenance and environment of fetched Argo data."""

    model_config = ConfigDict(frozen=True)

    src: str = "erddap"
    source: str = "erddap"
    argopy_version: str
    xarray_version: str
    fetch_timestamp: str
    row_count: int
    profile_count: int
    data_hash: str
    fetch_key: str


class FetchResult(BaseModel):
    """Deterministic result object containing fetched data, caching state, and QC audit report."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: FetchStatus
    data: Optional[pd.DataFrame] = None
    is_cached: bool = False
    cache_key: str = ""
    error_message: Optional[str] = None
    suggestion: Optional[str] = None
    metadata: Optional[FetchMetadata] = None
    qc_report: Optional[QCReport] = None
    effective_depth_range: DepthRange = Field(
        default_factory=lambda: DepthRange(min_depth=0.0, max_depth=500.0)
    )
    profile_count_verified: bool = False
    profile_count: Optional[int] = None
    coverage_status: Optional[CoverageStatus] = None


def count_unique_profiles(df: pd.DataFrame) -> int:
    """Count unique Argo profiles identified by (PLATFORM_NUMBER, CYCLE_NUMBER).

    In Argo data, multiple distinct floats (platforms) frequently have the same cycle number
    at the same time. Identifying profiles by CYCLE_NUMBER alone leads to under-counting.
    """
    if "PLATFORM_NUMBER" in df and "CYCLE_NUMBER" in df:
        return int(df[["PLATFORM_NUMBER", "CYCLE_NUMBER"]].drop_duplicates().shape[0])
    elif "CYCLE_NUMBER" in df:
        return int(df["CYCLE_NUMBER"].nunique())
    return 1 if len(df) > 0 else 0


def count_profiles_in_snapshot(
    spec: QuerySpec,
    snapshot_path: Optional[Path | str] = None,
) -> SnapshotProfileResult:
    """Evaluate coverage and count matching profiles from a local float-index Parquet snapshot.

    Compares query bounding box and date range against the snapshot's recorded coverage
    in its sidecar JSON (bbox, min_date, max_date, fetch_date).

    Returns:
        SnapshotProfileResult indicating whether the request is FULL, PARTIAL, or NOT_COVERED,
        along with the matching profile count.
    """
    if snapshot_path is None:
        snapshot_path = DEFAULT_FLOAT_INDEX_PATH
    path = Path(snapshot_path)
    if not path.exists():
        return SnapshotProfileResult(
            count=None,
            coverage=CoverageStatus.NOT_COVERED,
            details=f"Snapshot parquet file not found at {path}",
        )

    json_path = path.parent / f"{path.stem}.json"
    sidecar: dict[str, Any] = {}
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                sidecar = json.load(f)
        except Exception as err:
            logger.warning("Could not read sidecar JSON %s: %s", json_path, err)

    try:
        df = pd.read_parquet(path)
    except Exception as err:
        logger.warning("Error reading float index snapshot from %s: %s", path, err)
        return SnapshotProfileResult(
            count=None,
            coverage=CoverageStatus.NOT_COVERED,
            details=f"Error reading snapshot: {err}",
        )

    # 1. Determine snapshot spatial bounds
    snap_bbox = sidecar.get("bbox")
    if not snap_bbox and not df.empty:
        lon_col = "longitude" if "longitude" in df.columns else ("lon" if "lon" in df.columns else None)
        lat_col = "latitude" if "latitude" in df.columns else ("lat" if "lat" in df.columns else None)
        if lon_col and lat_col:
            snap_bbox = [
                float(df[lon_col].min()),
                float(df[lon_col].max()),
                float(df[lat_col].min()),
                float(df[lat_col].max()),
            ]

    # 2. Determine snapshot temporal bounds & fetch date
    snap_min_date = None
    snap_max_date = None
    snap_fetch_date = None

    if sidecar.get("min_date"):
        try:
            snap_min_date = pd.to_datetime(sidecar["min_date"]).date()
        except Exception:
            pass
    if sidecar.get("max_date"):
        try:
            snap_max_date = pd.to_datetime(sidecar["max_date"]).date()
        except Exception:
            pass
    if sidecar.get("fetch_date"):
        try:
            snap_fetch_date = pd.to_datetime(sidecar["fetch_date"]).date()
        except Exception:
            pass

    date_col_name = "date" if "date" in df.columns else ("time" if "time" in df.columns else None)
    if snap_min_date is None and not df.empty and date_col_name:
        valid_dates = df[date_col_name].dropna()
        if not valid_dates.empty:
            snap_min_date = pd.to_datetime(valid_dates.min()).date()
            if snap_max_date is None:
                snap_max_date = pd.to_datetime(valid_dates.max()).date()

    # 3. Assess spatial coverage
    spatial_status = "none"
    if snap_bbox and len(snap_bbox) == 4:
        s_lon_min, s_lon_max, s_lat_min, s_lat_max = (
            float(snap_bbox[0]),
            float(snap_bbox[1]),
            float(snap_bbox[2]),
            float(snap_bbox[3]),
        )
        q_lon_min, q_lon_max = float(spec.region.lon_min), float(spec.region.lon_max)
        q_lat_min, q_lat_max = float(spec.region.lat_min), float(spec.region.lat_max)

        lon_disjoint = (q_lon_min > s_lon_max) or (q_lon_max < s_lon_min)
        lat_disjoint = (q_lat_min > s_lat_max) or (q_lat_max < s_lat_min)

        if lon_disjoint or lat_disjoint:
            spatial_status = "none"
        elif (
            q_lon_min >= s_lon_min
            and q_lon_max <= s_lon_max
            and q_lat_min >= s_lat_min
            and q_lat_max <= s_lat_max
        ):
            spatial_status = "full"
        else:
            spatial_status = "partial"
    else:
        spatial_status = "none"

    # 4. Assess temporal coverage
    q_start = spec.date_range.start
    q_end = spec.date_range.end

    temporal_ceiling = None
    if snap_fetch_date is not None:
        temporal_ceiling = snap_fetch_date
    if snap_max_date is not None:
        if temporal_ceiling is None or snap_max_date < temporal_ceiling:
            temporal_ceiling = snap_max_date

    temporal_floor = snap_min_date

    temporal_status = "none"
    if temporal_floor is not None and q_end < temporal_floor:
        temporal_status = "none"
    elif temporal_ceiling is not None and q_start > temporal_ceiling:
        temporal_status = "none"
    else:
        extends_past_floor = (temporal_floor is not None and q_start < temporal_floor)
        extends_past_ceiling = (temporal_ceiling is not None and q_end > temporal_ceiling)

        if extends_past_floor or extends_past_ceiling:
            temporal_status = "partial"
        else:
            temporal_status = "full"

    # 5. Combined coverage
    if spatial_status == "none" or temporal_status == "none":
        combined_coverage = CoverageStatus.NOT_COVERED
    elif spatial_status == "full" and temporal_status == "full":
        combined_coverage = CoverageStatus.FULL
    else:
        combined_coverage = CoverageStatus.PARTIAL

    # 6. Count matching profiles in data
    if df.empty or combined_coverage == CoverageStatus.NOT_COVERED:
        matching_count = None if combined_coverage == CoverageStatus.NOT_COVERED else 0
        return SnapshotProfileResult(
            count=matching_count,
            coverage=combined_coverage,
            details=f"Spatial: {spatial_status}, Temporal: {temporal_status}",
        )

    lon_col = "longitude" if "longitude" in df.columns else ("lon" if "lon" in df.columns else None)
    lat_col = "latitude" if "latitude" in df.columns else ("lat" if "lat" in df.columns else None)
    mask = pd.Series(True, index=df.index)

    if lon_col:
        mask = mask & (df[lon_col] >= spec.region.lon_min) & (df[lon_col] <= spec.region.lon_max)
    if lat_col:
        mask = mask & (df[lat_col] >= spec.region.lat_min) & (df[lat_col] <= spec.region.lat_max)

    if date_col_name:
        date_series = pd.to_datetime(df[date_col_name], errors="coerce")
        start_dt = pd.to_datetime(spec.date_range.start)
        end_dt = pd.to_datetime(spec.date_range.end) + pd.Timedelta(days=1)
        mask = mask & (date_series >= start_dt) & (date_series < end_dt)

    df_filtered = df[mask]
    wmo_col = "wmo" if "wmo" in df_filtered.columns else ("PLATFORM_NUMBER" if "PLATFORM_NUMBER" in df_filtered.columns else None)
    cyc_col = "cycle_number" if "cycle_number" in df_filtered.columns else ("cycle" if "cycle" in df_filtered.columns else ("CYCLE_NUMBER" if "CYCLE_NUMBER" in df_filtered.columns else None))

    if wmo_col and cyc_col:
        count = int(df_filtered[[wmo_col, cyc_col]].drop_duplicates().shape[0])
    elif wmo_col:
        count = int(df_filtered[wmo_col].nunique())
    else:
        count = len(df_filtered)

    return SnapshotProfileResult(
        count=count,
        coverage=combined_coverage,
        details=f"Spatial: {spatial_status}, Temporal: {temporal_status}",
    )


def create_float_index_snapshot(
    box: Optional[list[float | str]] = None,
    output_dir: Path | str = "data",
    filename: str = "float_index.parquet",
    timeout: int = 60,
    index_fetcher_cls: Any = None,
) -> tuple[Path, Path]:
    """Fetch and store a local float-index Parquet snapshot with sidecar metadata JSON.

    Used strictly for discovery and pre-fetch guards (counting profiles), never for profile values.
    Records the snapshot's coverage (bbox, min/max date, fetch_date) in the sidecar JSON.
    Only stores the required metadata columns: (wmo, cycle, lat, lon, date).

    Args:
        box: Bounding box for index fetch: [lon_min, lon_max, lat_min, lat_max, date_min, date_max].
             Defaults to global bounds [-180.0, 180.0, -90.0, 90.0] if None.
        output_dir: Directory where parquet and json sidecar will be stored.
        filename: Name of the parquet file.
        timeout: Network timeout in seconds.
        index_fetcher_cls: Optional dependency-injected IndexFetcher class.

    Returns:
        tuple[Path, Path]: (parquet_path, json_path)
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / filename
    json_path = out_dir / filename.replace(".parquet", ".json")

    fetch_box = box if box is not None else [-180.0, 180.0, -90.0, 90.0]

    cls = index_fetcher_cls if index_fetcher_cls is not None else argopy.IndexFetcher
    engine = cls(src="erddap", api_timeout=timeout)
    df_raw = engine.region(fetch_box).to_dataframe()

    # Normalize columns to standard metadata: wmo, cycle_number, latitude, longitude, date
    df_clean = pd.DataFrame()
    if "wmo" in df_raw.columns:
        df_clean["wmo"] = df_raw["wmo"]
    elif "PLATFORM_NUMBER" in df_raw.columns:
        df_clean["wmo"] = df_raw["PLATFORM_NUMBER"]

    if "cycle_number" in df_raw.columns:
        df_clean["cycle_number"] = df_raw["cycle_number"]
    elif "cycle" in df_raw.columns:
        df_clean["cycle_number"] = df_raw["cycle"]
    elif "CYCLE_NUMBER" in df_raw.columns:
        df_clean["cycle_number"] = df_raw["CYCLE_NUMBER"]
    else:
        if "file" in df_raw.columns:
            extracted = df_raw["file"].str.extract(r"_(\d+)\.nc")
            df_clean["cycle_number"] = extracted[0].fillna(0).astype(int)
        else:
            df_clean["cycle_number"] = 0

    if "latitude" in df_raw.columns:
        df_clean["latitude"] = df_raw["latitude"]
    elif "lat" in df_raw.columns:
        df_clean["latitude"] = df_raw["lat"]
    elif "LATITUDE" in df_raw.columns:
        df_clean["latitude"] = df_raw["LATITUDE"]

    if "longitude" in df_raw.columns:
        df_clean["longitude"] = df_raw["longitude"]
    elif "lon" in df_raw.columns:
        df_clean["longitude"] = df_raw["lon"]
    elif "LONGITUDE" in df_raw.columns:
        df_clean["longitude"] = df_raw["LONGITUDE"]

    if "date" in df_raw.columns:
        df_clean["date"] = pd.to_datetime(df_raw["date"])
    elif "time" in df_raw.columns:
        df_clean["date"] = pd.to_datetime(df_raw["time"])
    elif "TIME" in df_raw.columns:
        df_clean["date"] = pd.to_datetime(df_raw["TIME"])

    df_clean.to_parquet(parquet_path, index=False)

    min_date_val = None
    max_date_val = None
    if not df_clean.empty and "date" in df_clean.columns:
        valid_dates = df_clean["date"].dropna()
        if not valid_dates.empty:
            min_date_val = pd.to_datetime(valid_dates.min()).date().isoformat()
            max_date_val = pd.to_datetime(valid_dates.max()).date().isoformat()

    if box is not None and len(box) >= 4:
        bbox_val = [float(box[0]), float(box[1]), float(box[2]), float(box[3])]
        if len(box) >= 6:
            min_date_val = str(box[4])
            max_date_val = str(box[5])
    elif not df_clean.empty and "longitude" in df_clean.columns and "latitude" in df_clean.columns:
        bbox_val = [
            float(df_clean["longitude"].min()),
            float(df_clean["longitude"].max()),
            float(df_clean["latitude"].min()),
            float(df_clean["latitude"].max()),
        ]
    else:
        bbox_val = [-180.0, 180.0, -90.0, 90.0]

    fetch_date_val = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    sidecar = {
        "fetch_date": fetch_date_val,
        "bbox": bbox_val,
        "min_date": min_date_val,
        "max_date": max_date_val,
        "row_count": len(df_clean),
        "source": "argopy.IndexFetcher snapshot",
        "description": "Local float-index Parquet snapshot of Argo metadata for pre-fetch discovery and guards",
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)

    return parquet_path, json_path
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)

    return parquet_path, json_path


def count_matching_profiles_via_index(
    spec: QuerySpec,
    timeout: int = 30,
    index_fetcher_cls: Any = None,
) -> Optional[int]:
    """Query argopy.IndexFetcher over the network to get profile count.

    Note: Network pre-fetch takes 40-50s on remote ERDDAP; use count_profiles_in_snapshot
    for standard offline pre-fetch guards.
    """
    box = [
        float(spec.region.lon_min),
        float(spec.region.lon_max),
        float(spec.region.lat_min),
        float(spec.region.lat_max),
        spec.date_range.start.isoformat(),
        spec.date_range.end.isoformat(),
    ]
    cls = index_fetcher_cls if index_fetcher_cls is not None else argopy.IndexFetcher
    try:
        engine = cls(src="erddap", api_timeout=timeout)
        df_idx = engine.region(box).to_dataframe()
        return len(df_idx)
    except Exception as err:
        logger.warning("IndexFetcher network profile count failed: %s", err)
        return None


def compute_canonical_data_hash(df: Optional[pd.DataFrame]) -> str:
    """Compute a canonical SHA-256 hash invariant to row order, column order, and float representation.

    Fixed column order: sorted alphabetically.
    Rows sorted by: (PLATFORM_NUMBER, CYCLE_NUMBER, PRES) if present, or all columns.
    Fixed float precision: rounded to 4 decimal places.
    """
    if df is None or len(df) == 0:
        return ""

    df_norm = df.copy()

    # Sort columns alphabetically
    cols = sorted(str(c) for c in df_norm.columns)
    df_norm = df_norm[cols]

    # Round floating-point columns to fixed precision (4 decimal places)
    for c in cols:
        if pd.api.types.is_float_dtype(df_norm[c]):
            df_norm[c] = df_norm[c].round(4)

    # Sort rows by (PLATFORM_NUMBER, CYCLE_NUMBER, PRES) if available
    sort_keys = [k for k in ["PLATFORM_NUMBER", "CYCLE_NUMBER", "PRES"] if k in cols]
    if sort_keys:
        df_norm = df_norm.sort_values(by=sort_keys, ignore_index=True)
    else:
        df_norm = df_norm.sort_values(by=cols, ignore_index=True)

    # Deterministic CSV bytes serialization
    csv_bytes = df_norm.to_csv(index=False, lineterminator="\n", float_format="%.4f").encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()


_compute_data_hash = compute_canonical_data_hash


def is_cache_entry_valid(
    metadata: FetchMetadata,
    mode: DataMode,
    cache_expiry_days: int = DEFAULT_CACHE_EXPIRY_DAYS,
    research_cache_expiry_days: int = DEFAULT_RESEARCH_CACHE_EXPIRY_DAYS,
    reference_time: Optional[datetime] = None,
    current_argopy_version: Optional[str] = None,
) -> bool:
    """Determine if a cached entry remains valid.

    Rules:
      - RESEARCH mode: Expires if older than research_cache_expiry_days (default 90 days),
        or if the installed argopy version changes.
      - STANDARD and EXPERT mode: Expires after cache_expiry_days (default 7 days).
    """
    if current_argopy_version is None:
        current_argopy_version = str(argopy.__version__)

    if reference_time is None:
        reference_time = datetime.utcnow()

    try:
        ts_str = metadata.fetch_timestamp.replace("Z", "+00:00")
        cached_dt = datetime.fromisoformat(ts_str)
        if cached_dt.tzinfo is not None and reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        age_seconds = (reference_time - cached_dt).total_seconds()
    except Exception as err:
        logger.warning("Failed parsing fetch_timestamp '%s': %s", metadata.fetch_timestamp, err)
        return False

    if mode == DataMode.RESEARCH:
        # Invalidate if argopy library version changed
        if metadata.argopy_version != current_argopy_version:
            return False
        # Invalidate if older than 90 days
        return age_seconds <= (research_cache_expiry_days * 86400)

    # Standard and Expert modes expire after cache_expiry_days (default 7 days)
    return age_seconds <= (cache_expiry_days * 86400)


def _build_empty_result(
    spec: QuerySpec,
    fetch_key: str,
    effective_depth_range: DepthRange,
    today: Optional[date] = None,
    profile_count_verified: bool = False,
    profile_count: Optional[int] = None,
    coverage_status: Optional[CoverageStatus] = None,
) -> FetchResult:
    """Construct an EMPTY FetchResult with domain-aware guidance for recent research queries."""
    if today is None:
        today = date.today()

    days_since_end = (today - spec.date_range.end).days
    is_recent_window = days_since_end <= 365

    if spec.mode == DataMode.RESEARCH and is_recent_window:
        msg = (
            "No delayed-mode Argo data found for this recent time window. "
            "Argo delayed-mode quality control (DMQC) for research mode typically takes 6 to 12 months to complete and publish."
        )
        suggestion = (
            "Try standard mode (e.g. 'real-time' or 'near real-time') for observations within the last 12 months, "
            "or query an earlier window (older than 12 months) where delayed-mode research data is available."
        )
    else:
        msg = "No Argo profiles found for the specified region, date range, and depth bounds."
        suggestion = "Try widening the geographic bounding box or expanding the date range."

    return FetchResult(
        status=FetchStatus.EMPTY,
        data=None,
        is_cached=False,
        cache_key=fetch_key,
        error_message=msg,
        suggestion=suggestion,
        effective_depth_range=effective_depth_range,
        profile_count_verified=profile_count_verified,
        profile_count=profile_count,
        coverage_status=coverage_status,
    )


def fetch(
    spec: QuerySpec,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    timeout: int = 60,
    max_request_size: float = DEFAULT_MAX_REQUEST_SIZE,
    max_profile_count: Optional[int] = DEFAULT_MAX_PROFILE_COUNT,
    float_index_path: Optional[Path | str] = None,
    cache_expiry_days: int = DEFAULT_CACHE_EXPIRY_DAYS,
    research_cache_expiry_days: int = DEFAULT_RESEARCH_CACHE_EXPIRY_DAYS,
    today: Optional[date] = None,
    reference_time: Optional[datetime] = None,
    src: str = "erddap",
    fetcher_engine: Any = None,
    index_fetcher_cls: Any = None,
) -> FetchResult:
    """Fetch Argo profile observations according to a validated QuerySpec.

    Uses argopy DataFetcher with the mode passed explicitly from the spec.
    Defaults depth range to 0-500 dbar when none is specified.
    Enforces size cap (max_request_size) and profile count ceiling (max_profile_count) by default.
    Evaluates profile count guard using local float-index Parquet snapshot (fast, offline).
    Caches fetched datasets as Parquet with a sidecar JSON in the cache directory.
    Enforces cache expiration: 7 days for standard/expert, 90 days for research (or argopy version change).

    Args:
        spec: Validated QuerySpec defining region, date_range, depth_range, variables, and mode.
        cache_dir: Path to directory for Parquet and JSON cache (defaults to 'cache/').
        force_refresh: If True, bypasses local cache and fetches remotely.
        timeout: Network timeout in seconds for remote data server requests.
        max_request_size: Cost threshold (provisional 15,000) above which requests are rejected.
        max_profile_count: Profile count ceiling (provisional 100) above which requests are rejected.
        float_index_path: Path to local float index parquet snapshot for profile counting.
        cache_expiry_days: Cache expiration period in days for standard/expert entries (default: 7).
        research_cache_expiry_days: Cache expiration period in days for research entries (default: 90).
        today: Reference date for relative date analysis (default: date.today()).
        reference_time: Reference timestamp for cache expiry evaluation (default: datetime.utcnow()).
        src: Data source (default: 'erddap').
        fetcher_engine: Optional dependency-injected data fetcher class (defaults to argopy.DataFetcher).
        index_fetcher_cls: Optional dependency-injected index fetcher class for network checks if requested.

    Returns:
        FetchResult with status, data (if successful), cache indicator, and QC report.
    """
    if today is None:
        today = date.today()

    # Default depth range to 0-500 dbar when spec has none
    effective_depth_range = spec.depth_range or DepthRange(min_depth=0.0, max_depth=500.0)

    # 1. Spec validation & size cap enforcement (active by default with max_request_size = 15,000)
    try:
        validate_spec(spec, max_request_size=max_request_size)
    except OversizedRequestError as err:
        return FetchResult(
            status=FetchStatus.OVERSIZED,
            data=None,
            is_cached=False,
            cache_key=spec.fetch_key(),
            error_message=str(err),
            suggestion=err.suggestion,
            effective_depth_range=effective_depth_range,
        )
    except SpecValidationError as err:
        return FetchResult(
            status=FetchStatus.ERROR,
            data=None,
            is_cached=False,
            cache_key=spec.fetch_key(),
            error_message=str(err),
            suggestion="Please check the query parameters and ensure valid bounds and dates.",
            effective_depth_range=effective_depth_range,
        )

    # 2. Profile Count Guard & Coverage Evaluation
    profile_count_verified = False
    estimated_profile_count: Optional[int] = None
    coverage_status: Optional[CoverageStatus] = None

    if max_profile_count is not None:
        # Check network index only if explicit mock/engine injected; otherwise use local snapshot
        if index_fetcher_cls is not None:
            n_profs = count_matching_profiles_via_index(
                spec,
                timeout=timeout,
                index_fetcher_cls=index_fetcher_cls,
            )
            if n_profs is not None:
                estimated_profile_count = n_profs
                profile_count_verified = True
                coverage_status = CoverageStatus.FULL
                if n_profs > max_profile_count:
                    return FetchResult(
                        status=FetchStatus.OVERSIZED,
                        data=None,
                        is_cached=False,
                        cache_key=spec.fetch_key(),
                        error_message=(
                            f"Estimated profile count ({n_profs}) exceeds the maximum limit ({max_profile_count})."
                        ),
                        suggestion=(
                            "Please narrow your query by selecting a smaller region, a shorter date window, or a shallower depth range."
                        ),
                        effective_depth_range=effective_depth_range,
                        profile_count_verified=True,
                        profile_count=n_profs,
                        coverage_status=CoverageStatus.FULL,
                    )
        else:
            snap_res = count_profiles_in_snapshot(spec, snapshot_path=float_index_path)
            coverage_status = snap_res.coverage
            estimated_profile_count = snap_res.count

            if snap_res.coverage == CoverageStatus.FULL:
                profile_count_verified = True
                if snap_res.count is not None and snap_res.count > max_profile_count:
                    return FetchResult(
                        status=FetchStatus.OVERSIZED,
                        data=None,
                        is_cached=False,
                        cache_key=spec.fetch_key(),
                        error_message=(
                            f"Estimated profile count ({snap_res.count}) exceeds the maximum limit ({max_profile_count})."
                        ),
                        suggestion=(
                            "Please narrow your query by selecting a smaller region, a shorter date window, or a shallower depth range."
                        ),
                        effective_depth_range=effective_depth_range,
                        profile_count_verified=True,
                        profile_count=snap_res.count,
                        coverage_status=CoverageStatus.FULL,
                    )
            else:
                # Requirement 2: If the request is partly or not covered, do NOT treat count as 0;
                # apply only the cost cap and set profile_count_verified = False
                profile_count_verified = False

    # 3. Cache key and storage setup
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    fetch_key = spec.fetch_key()
    parquet_path = cache_dir / f"{fetch_key}.parquet"
    sidecar_path = cache_dir / f"{fetch_key}.json"

    # 4. Check cache hit
    if not force_refresh and parquet_path.exists() and sidecar_path.exists():
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
            metadata = FetchMetadata(**meta_dict)

            # Evaluate cache expiration rules (7 days standard/expert, 90 days / argopy version for research)
            if is_cache_entry_valid(
                metadata=metadata,
                mode=spec.mode,
                cache_expiry_days=cache_expiry_days,
                research_cache_expiry_days=research_cache_expiry_days,
                reference_time=reference_time,
            ):
                df = pd.read_parquet(parquet_path)
                qc_report = audit_qc(df, spec.variables, spec.mode)
                return FetchResult(
                    status=FetchStatus.SUCCESS,
                    data=df,
                    is_cached=True,
                    cache_key=fetch_key,
                    metadata=metadata,
                    qc_report=qc_report,
                    effective_depth_range=effective_depth_range,
                    profile_count_verified=profile_count_verified,
                    profile_count=estimated_profile_count,
                    coverage_status=coverage_status,
                )
            else:
                logger.info(
                    "Cache entry for key %s has expired (mode=%s). Re-fetching.",
                    fetch_key,
                    spec.mode.value,
                )
        except Exception as cache_err:
            logger.warning("Failed reading cached files for key %s: %s. Re-fetching.", fetch_key, cache_err)

    # 5. Remote fetch execution
    # Construct standard argopy region box: [lon_min, lon_max, lat_min, lat_max, dpt_min, dpt_max, date_min, date_max]
    box = [
        float(spec.region.lon_min),
        float(spec.region.lon_max),
        float(spec.region.lat_min),
        float(spec.region.lat_max),
        float(effective_depth_range.min_depth),
        float(effective_depth_range.max_depth),
        spec.date_range.start.isoformat(),
        spec.date_range.end.isoformat(),
    ]

    # Explicit mode passed from spec (never the library default)
    mode_str = spec.mode.value
    fetcher_cls = fetcher_engine if fetcher_engine is not None else argopy.DataFetcher

    try:
        engine = fetcher_cls(mode=mode_str, src=src, api_timeout=timeout)
        df = engine.region(box).to_dataframe()
    except (FileNotFoundError, argopy.errors.DataNotFound, argopy.errors.NoData, argopy.errors.NoDataLeft):
        return _build_empty_result(
            spec,
            fetch_key,
            effective_depth_range,
            today=today,
            profile_count_verified=profile_count_verified,
            profile_count=estimated_profile_count,
            coverage_status=coverage_status,
        )
    except TimeoutError:
        return FetchResult(
            status=FetchStatus.TIMEOUT,
            data=None,
            is_cached=False,
            cache_key=fetch_key,
            error_message="Remote data request timed out.",
            suggestion="The remote ERDDAP server took too long to respond. Try narrowing your query region or try again later.",
            effective_depth_range=effective_depth_range,
            profile_count_verified=profile_count_verified,
            profile_count=estimated_profile_count,
            coverage_status=coverage_status,
        )
    except Exception as err:
        err_str = str(err).lower()
        if "timeout" in err_str or "timed out" in err_str:
            return FetchResult(
                status=FetchStatus.TIMEOUT,
                data=None,
                is_cached=False,
                cache_key=fetch_key,
                error_message="Remote data request timed out.",
                suggestion="The remote ERDDAP server took too long to respond. Try narrowing your query region or try again later.",
                effective_depth_range=effective_depth_range,
                profile_count_verified=profile_count_verified,
                profile_count=estimated_profile_count,
                coverage_status=coverage_status,
            )
        if "not found" in err_str or "nodataleft" in err_str or "empty" in err_str:
            return _build_empty_result(
                spec,
                fetch_key,
                effective_depth_range,
                today=today,
                profile_count_verified=profile_count_verified,
                profile_count=estimated_profile_count,
                coverage_status=coverage_status,
            )
        return FetchResult(
            status=FetchStatus.ERROR,
            data=None,
            is_cached=False,
            cache_key=fetch_key,
            error_message=f"Argo fetch failed: {err}",
            suggestion="Check remote data server connectivity or adjust query parameters.",
            effective_depth_range=effective_depth_range,
            profile_count_verified=profile_count_verified,
            profile_count=estimated_profile_count,
            coverage_status=coverage_status,
        )

    # 6. Handle empty DataFrame results
    if df is None or len(df) == 0:
        return _build_empty_result(
            spec,
            fetch_key,
            effective_depth_range,
            today=today,
            profile_count_verified=profile_count_verified,
            profile_count=estimated_profile_count,
            coverage_status=coverage_status,
        )

    # 7. Save Parquet and sidecar JSON metadata
    profile_count = count_unique_profiles(df)

    try:
        df.to_parquet(parquet_path, index=False)
        data_hash = _compute_data_hash(df)

        metadata = FetchMetadata(
            src=src,
            source=src,
            argopy_version=str(argopy.__version__),
            xarray_version=str(xr.__version__),
            fetch_timestamp=datetime.utcnow().isoformat() + "Z",
            row_count=len(df),
            profile_count=profile_count,
            data_hash=data_hash,
            fetch_key=fetch_key,
        )

        with open(sidecar_path, "w", encoding="utf-8") as f:
            f.write(metadata.model_dump_json(indent=2))

    except Exception as save_err:
        logger.error("Failed saving cached data/sidecar for key %s: %s", fetch_key, save_err)
        data_hash = _compute_data_hash(df)
        metadata = FetchMetadata(
            src=src,
            source=src,
            argopy_version=str(argopy.__version__),
            xarray_version=str(xr.__version__),
            fetch_timestamp=datetime.utcnow().isoformat() + "Z",
            row_count=len(df),
            profile_count=profile_count,
            data_hash=data_hash,
            fetch_key=fetch_key,
        )

    # 8. Audit QC without dropping rows
    qc_report = audit_qc(df, spec.variables, spec.mode)

    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=False,
        cache_key=fetch_key,
        metadata=metadata,
        qc_report=qc_report,
        effective_depth_range=effective_depth_range,
        profile_count_verified=profile_count_verified,
        profile_count=estimated_profile_count,
        coverage_status=coverage_status,
    )
