"""Local Argo Float Index management, spatial-temporal querying, and metadata coverage.

Provides fast, in-memory evaluation of float positions, profile counts, float tracks,
and sample selection using the local Parquet float index snapshot without touching network.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any, Optional, Union
import pandas as pd

from .spec import BoundingBox, DateRange

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FLOAT_INDEX_PATH = PROJECT_ROOT / "data" / "float_index.parquet"
DEFAULT_FLOAT_INDEX_JSON = PROJECT_ROOT / "data" / "float_index.json"


class CoverageStatus(str, Enum):
    """Temporal and spatial coverage of a query against the float index."""

    FULL = "full"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"


# Ocean basin canonical mapping
BASIN_CODE_MAP = {
    "indian ocean": "I",
    "indian": "I",
    "i": "I",
    "pacific ocean": "P",
    "pacific": "P",
    "p": "P",
    "atlantic ocean": "A",
    "atlantic": "A",
    "a": "A",
}


def _resolve_basin_code(name_or_code: str) -> Optional[str]:
    """Return 'A', 'I', or 'P' if string matches a known ocean basin name or code."""
    key = str(name_or_code).strip().lower()
    return BASIN_CODE_MAP.get(key)


class FloatIndex:
    """In-memory wrapper for the local Argo float index."""

    def __init__(
        self,
        df: Optional[pd.DataFrame] = None,
        metadata: Optional[dict[str, Any]] = None,
        parquet_path: Optional[Path] = None,
    ) -> None:
        self.df: pd.DataFrame = df if df is not None else pd.DataFrame()
        self.metadata: dict[str, Any] = metadata or {}
        self.parquet_path: Optional[Path] = parquet_path
        self.is_available: bool = df is not None and not df.empty

        self.min_date: Optional[date] = None
        self.max_date: Optional[date] = None
        self.build_date: Optional[datetime] = None

        if self.is_available:
            self._init_bounds()

    def _init_bounds(self) -> None:
        """Parse temporal bounds from metadata or underlying DataFrame."""
        if "min_date" in self.metadata:
            try:
                self.min_date = date.fromisoformat(str(self.metadata["min_date"])[:10])
            except Exception:
                pass
        if "max_date" in self.metadata:
            try:
                self.max_date = date.fromisoformat(str(self.metadata["max_date"])[:10])
            except Exception:
                pass

        if self.min_date is None and "date" in self.df.columns and not self.df.empty:
            valid_d = self.df["date"].dropna()
            if not valid_d.empty:
                self.min_date = pd.to_datetime(valid_d.min()).date()
                self.max_date = pd.to_datetime(valid_d.max()).date()

        if "build_date" in self.metadata:
            try:
                b_str = str(self.metadata["build_date"]).replace("Z", "+00:00")
                self.build_date = datetime.fromisoformat(b_str)
            except Exception:
                pass

    def query_profiles(
        self,
        bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
        date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
        delayed_only: bool = False,
    ) -> pd.DataFrame:
        """Query matching float profiles by bounding box or basin, date range, and delayed mode.

        Supports antimeridian crossing boxes (lon_min > lon_max) as two disjoint longitude spans.
        """
        if not self.is_available or self.df.empty:
            return pd.DataFrame()

        mask = pd.Series(True, index=self.df.index)

        # 1. Geographic / Basin filtering
        if bbox_or_basin is not None:
            if isinstance(bbox_or_basin, str):
                basin_code = _resolve_basin_code(bbox_or_basin)
                if basin_code:
                    mask &= (self.df["ocean"].astype(str) == basin_code)
                else:
                    return pd.DataFrame()
            else:
                if isinstance(bbox_or_basin, BoundingBox):
                    lon_min = float(bbox_or_basin.lon_min)
                    lon_max = float(bbox_or_basin.lon_max)
                    lat_min = float(bbox_or_basin.lat_min)
                    lat_max = float(bbox_or_basin.lat_max)
                else:
                    lon_min, lon_max, lat_min, lat_max = (
                        float(bbox_or_basin[0]),
                        float(bbox_or_basin[1]),
                        float(bbox_or_basin[2]),
                        float(bbox_or_basin[3]),
                    )

                # Antimeridian check
                if lon_min > lon_max:
                    lon_cond = (self.df["longitude"] >= lon_min) | (self.df["longitude"] <= lon_max)
                else:
                    lon_cond = (self.df["longitude"] >= lon_min) & (self.df["longitude"] <= lon_max)

                lat_cond = (self.df["latitude"] >= lat_min) & (self.df["latitude"] <= lat_max)
                mask &= (lon_cond & lat_cond)

        # 2. Temporal filtering
        if date_range is not None:
            if isinstance(date_range, DateRange):
                start_d = date_range.start
                end_d = date_range.end
            else:
                start_d, end_d = date_range[0], date_range[1]

            start_dt = pd.to_datetime(start_d)
            end_dt = pd.to_datetime(end_d) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
            mask &= (self.df["date"] >= start_dt) & (self.df["date"] <= end_dt)

        # 3. Delayed mode filtering
        if delayed_only:
            if "is_delayed" in self.df.columns:
                mask &= (self.df["is_delayed"] == True)  # noqa: E712

        return self.df[mask].copy()

    def count_profiles(
        self,
        bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
        date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
        delayed_only: bool = False,
    ) -> int:
        """Return exact count of matching float profiles."""
        if not self.is_available:
            return 0
        df_sub = self.query_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range, delayed_only=delayed_only)
        return len(df_sub)

    def last_positions(
        self,
        bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
        date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    ) -> pd.DataFrame:
        """Return the latest position for each distinct float within query bounds."""
        df_sub = self.query_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range)
        if df_sub.empty:
            return pd.DataFrame()
        # Sort by date ascending, then keep last observation per WMO
        sorted_df = df_sub.sort_values("date")
        return sorted_df.drop_duplicates(subset=["wmo"], keep="last").reset_index(drop=True)

    def tracks(
        self,
        bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
        date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    ) -> pd.DataFrame:
        """Return all profile positions sorted by float WMO and chronological date."""
        df_sub = self.query_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range)
        if df_sub.empty:
            return pd.DataFrame()
        return df_sub.sort_values(["wmo", "date"]).reset_index(drop=True)

    def coverage_status(self, date_range: Union[DateRange, tuple[Any, Any]]) -> CoverageStatus:
        """Evaluate whether query date range is fully, partially, or not covered by the index."""
        if not self.is_available or self.min_date is None or self.max_date is None:
            return CoverageStatus.NOT_COVERED

        if isinstance(date_range, DateRange):
            q_start, q_end = date_range.start, date_range.end
        else:
            q_start, q_end = date_range[0], date_range[1]

        if hasattr(q_start, "date"):
            q_start = q_start.date()
        if hasattr(q_end, "date"):
            q_end = q_end.date()

        if q_end < self.min_date or q_start > self.max_date:
            return CoverageStatus.NOT_COVERED
        if q_start >= self.min_date and q_end <= self.max_date:
            return CoverageStatus.FULL
        return CoverageStatus.PARTIAL

    def snapshot_age_days(self, today: Optional[date] = None) -> Optional[int]:
        """Return age of the index snapshot in days relative to reference date (default: today)."""
        if not self.is_available:
            return None
        ref_today = today or date.today()
        if self.build_date is not None:
            return max(0, (ref_today - self.build_date.date()).days)
        if self.max_date is not None:
            return max(0, (ref_today - self.max_date).days)
        return None


@lru_cache(maxsize=4)
def _load_float_index_from_disk(parquet_path_str: str) -> FloatIndex:
    """Internal cached loader for FloatIndex from a specific filesystem path."""
    p_path = Path(parquet_path_str)
    if not p_path.exists():
        logger.warning("Float index parquet file not found at %s", p_path)
        return FloatIndex(df=None, metadata={}, parquet_path=p_path)

    j_path = p_path.with_suffix(".json")
    metadata: dict[str, Any] = {}
    if j_path.exists():
        try:
            with open(j_path, "r", encoding="utf-8") as jf:
                metadata = json.load(jf)
        except Exception as err:
            logger.warning("Failed to load float index sidecar JSON %s: %s", j_path, err)

    try:
        df = pd.read_parquet(p_path)
        return FloatIndex(df=df, metadata=metadata, parquet_path=p_path)
    except Exception as err:
        logger.error("Failed to read float index parquet file %s: %s", p_path, err)
        return FloatIndex(df=None, metadata=metadata, parquet_path=p_path)


def load_float_index(parquet_path: Optional[Path | str] = None) -> FloatIndex:
    """Load the local float index singleton.

    Uses st.cache_resource if running within Streamlit, otherwise cached via lru_cache.
    Returns an index object with is_available=False if the index file is missing, never crashing.
    """
    path = Path(parquet_path) if parquet_path is not None else DEFAULT_FLOAT_INDEX_PATH
    return _load_float_index_from_disk(str(path.resolve()))


# ==============================================================================
# CONVENIENCE MODULE-LEVEL FUNCTIONS
# ==============================================================================


def query_profiles(
    bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
    date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    delayed_only: bool = False,
    index: Optional[FloatIndex] = None,
) -> pd.DataFrame:
    """Query float profiles matching geographic bounds and date range."""
    idx = index or load_float_index()
    return idx.query_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range, delayed_only=delayed_only)


def count_profiles(
    bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
    date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    delayed_only: bool = False,
    index: Optional[FloatIndex] = None,
) -> int:
    """Count float profiles matching geographic bounds and date range."""
    idx = index or load_float_index()
    return idx.count_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range, delayed_only=delayed_only)


def last_positions(
    bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
    date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    index: Optional[FloatIndex] = None,
) -> pd.DataFrame:
    """Return latest position for each distinct float."""
    idx = index or load_float_index()
    return idx.last_positions(bbox_or_basin=bbox_or_basin, date_range=date_range)


def tracks(
    bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, None] = None,
    date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    index: Optional[FloatIndex] = None,
) -> pd.DataFrame:
    """Return float positions sorted by float and date."""
    idx = index or load_float_index()
    return idx.tracks(bbox_or_basin=bbox_or_basin, date_range=date_range)


def coverage_status(
    date_range: Union[DateRange, tuple[Any, Any]],
    index: Optional[FloatIndex] = None,
) -> CoverageStatus:
    """Evaluate temporal coverage status of query against the index."""
    idx = index or load_float_index()
    return idx.coverage_status(date_range)


def snapshot_age_days(
    today: Optional[date] = None,
    index: Optional[FloatIndex] = None,
) -> Optional[int]:
    """Return age of float index in days."""
    idx = index or load_float_index()
    return idx.snapshot_age_days(today)
