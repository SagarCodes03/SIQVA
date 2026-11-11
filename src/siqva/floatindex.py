"""Local Argo Float Index management, spatial-temporal querying, and metadata coverage.

Provides fast, in-memory evaluation of float positions, profile counts, float tracks,
and sample selection using the local Parquet float index snapshot without touching network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from functools import lru_cache
import hashlib
import json
import logging
import math
from pathlib import Path
import random
from typing import Any, Optional, Union
import pandas as pd

from .spec import BoundingBox, DateRange

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FLOAT_INDEX_PATH = PROJECT_ROOT / "data" / "float_index.parquet"
DEFAULT_FLOAT_INDEX_JSON = PROJECT_ROOT / "data" / "float_index.json"

SAMPLE_DEFAULT: int = 12
SAMPLE_STEPS: tuple[int, ...] = (12, 24, 48)
SAMPLE_MAX: int = 50


@dataclass(frozen=True)
class SamplePick:
    """A single selected Argo profile pick for sample-based visualization."""

    wmo: int
    cycle: int
    date: str
    lat: float
    lon: float
    is_delayed: bool = False
    institution: str = ""

    def __getitem__(self, item: str | int) -> Any:
        """Allow dict-like or tuple-like indexing."""
        if isinstance(item, int):
            return (self.wmo, self.cycle, self.date, self.lat, self.lon)[item]
        return getattr(self, item)


@dataclass
class SampleSelection:
    """Result of deterministic sample selection over matching profiles."""

    picks: list[SamplePick]
    method: str
    seed: int
    n_available: int
    n_requested: int
    warning: Optional[str] = None

    def __iter__(self):
        """Allows unpacking: picks, method = index.select_sample(...)"""
        return iter((self.picks, self.method))

    def __len__(self) -> int:
        return len(self.picks)


def compute_sample_seed(fetch_key: str, build_date: Any) -> int:
    """Compute a deterministic 32-bit integer seed from fetch key and index build date."""
    b_str = str(build_date or "")
    combined = f"{fetch_key}_{b_str}".encode("utf-8")
    h = hashlib.sha256(combined).hexdigest()
    return int(h[:8], 16)


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

    def select_sample(
        self,
        bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, Any, None] = None,
        date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
        n: int = SAMPLE_DEFAULT,
        mode: Union[str, Any] = "research",
        fetch_key: str = "",
        seed: Optional[int] = None,
    ) -> SampleSelection:
        """Deterministically select n profiles spread evenly across space and time.

        Picks distinct floats when available and applies research/standard mode filtering.
        """
        # If a QuerySpec was passed directly
        if hasattr(bbox_or_basin, "region") and hasattr(bbox_or_basin, "date_range"):
            spec = bbox_or_basin
            bbox_or_basin = spec.basin or spec.region
            date_range = spec.date_range
            mode = getattr(spec.mode, "value", spec.mode)
            if not fetch_key and hasattr(spec, "fetch_key"):
                fetch_key = spec.fetch_key()

        # Handle DataMode enum or string
        mode_str = str(getattr(mode, "value", mode)).lower()
        is_research = "research" in mode_str

        # Cap n
        n_requested = n
        if n <= 0:
            return SampleSelection(
                picks=[],
                method="Requested 0 profiles",
                seed=0,
                n_available=0,
                n_requested=0,
            )
        n_target = min(n, SAMPLE_MAX)

        # Deterministic seed
        if seed is None:
            build_ref = self.metadata.get("build_date") or self.build_date or self.max_date
            seed = compute_sample_seed(fetch_key, build_ref)

        rng = random.Random(seed)

        if not self.is_available or self.df.empty:
            return SampleSelection(
                picks=[],
                method="Float index unavailable",
                seed=seed,
                n_available=0,
                n_requested=n_requested,
            )

        # 1. Filter candidates by spatial/basin and date bounds
        df_all = self.query_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range, delayed_only=False)
        n_total_avail = len(df_all)

        warning: Optional[str] = None
        if is_research:
            # Research mode requires delayed-mode profiles
            df_candidates = self.query_profiles(bbox_or_basin=bbox_or_basin, date_range=date_range, delayed_only=True)
            n_delayed = len(df_candidates)
            if n_delayed < n_target:
                warning = (
                    f"Only {n_delayed} delayed-mode profiles available in research mode "
                    f"(requested {n_target} out of {n_total_avail} total profiles). "
                    "For more recent observations, consider standard mode."
                )
        else:
            df_candidates = df_all

        n_avail = len(df_candidates)
        if df_candidates.empty:
            method_desc = (
                f"0 delayed-mode profiles available in research mode (out of {n_total_avail} total). Suggest standard mode."
                if (is_research and n_total_avail > 0)
                else "No matching profiles found in region/period."
            )
            return SampleSelection(
                picks=[],
                method=method_desc,
                seed=seed,
                n_available=0,
                n_requested=n_requested,
                warning=warning,
            )

        # Helper to build SamplePick
        def _to_pick(row: pd.Series) -> SamplePick:
            wmo_val = int(row["wmo"])
            cyc_val = int(row["cycle"] if "cycle" in row else row["cycle_number"])
            date_str = str(pd.to_datetime(row["date"]).date()) if pd.notnull(row["date"]) else ""
            lat_val = round(float(row["latitude"]), 4)
            lon_val = round(float(row["longitude"]), 4)
            is_del = bool(row.get("is_delayed", False))
            inst = str(row.get("institution", ""))
            return SamplePick(
                wmo=wmo_val,
                cycle=cyc_val,
                date=date_str,
                lat=lat_val,
                lon=lon_val,
                is_delayed=is_del,
                institution=inst,
            )

        # If available profiles are fewer than or equal to n_target, return all
        if n_avail <= n_target:
            sorted_candidates = df_candidates.sort_values(by=["date", "wmo", "cycle"]).reset_index(drop=True)
            picks = [_to_pick(row) for _, row in sorted_candidates.iterrows()]
            method = f"Selected all {len(picks)} available profiles (requested {n_target})."
            return SampleSelection(
                picks=picks,
                method=method,
                seed=seed,
                n_available=n_avail,
                n_requested=n_requested,
                warning=warning,
            )

        # 2. Divide space and time into grid cells and slices
        n_t = max(1, round(math.sqrt(n_target)))
        n_s = int(math.ceil(n_target / n_t))
        n_lat = max(1, round(math.sqrt(n_s)))
        n_lon = int(math.ceil(n_s / n_lat))

        df_c = df_candidates.copy()
        lons = df_c["longitude"].astype(float)
        lats = df_c["latitude"].astype(float)
        dates = pd.to_datetime(df_c["date"])

        # Check if coordinates span antimeridian
        is_antimeridian = False
        if isinstance(bbox_or_basin, BoundingBox) and bbox_or_basin.lon_min > bbox_or_basin.lon_max:
            is_antimeridian = True
            lon_offset_min = float(bbox_or_basin.lon_min)
            norm_lons = lons % 360
            adj_lons = norm_lons.apply(lambda x: x if x >= lon_offset_min else x + 360)
            lon_min_val, lon_max_val = lon_offset_min, float(bbox_or_basin.lon_max) + 360
        else:
            adj_lons = lons
            lon_min_val, lon_max_val = float(lons.min()), float(lons.max())

        lat_min_val, lat_max_val = float(lats.min()), float(lats.max())
        date_min_val, date_max_val = dates.min(), dates.max()

        time_span = max((date_max_val - date_min_val).total_seconds(), 1.0)
        lat_span = max(lat_max_val - lat_min_val, 0.001)
        lon_span = max(lon_max_val - lon_min_val, 0.001)

        t_bins = ((dates - date_min_val).dt.total_seconds() / time_span * n_t).astype(int).clip(0, n_t - 1)
        lat_bins = ((lats - lat_min_val) / lat_span * n_lat).astype(int).clip(0, n_lat - 1)
        lon_bins = ((adj_lons - lon_min_val) / lon_span * n_lon).astype(int).clip(0, n_lon - 1)

        df_c["_t_bin"] = t_bins
        df_c["_space_bin"] = lat_bins * n_lon + lon_bins
        df_c["_bin_id"] = list(zip(df_c["_t_bin"], df_c["_space_bin"]))

        # Group by bin
        bins_dict: dict[tuple[int, int], list[pd.Series]] = {}
        for _, row in df_c.iterrows():
            bid = row["_bin_id"]
            bins_dict.setdefault(bid, []).append(row)

        all_bin_ids = sorted(bins_dict.keys())
        rng.shuffle(all_bin_ids)

        picked_rows: list[pd.Series] = []
        wmo_pick_counts: dict[int, int] = {}
        used_indices: set[Any] = set()

        def _pick_best_from_bin(candidate_rows: list[pd.Series]) -> Optional[pd.Series]:
            avail = [r for r in candidate_rows if r.name not in used_indices]
            if not avail:
                return None
            min_wmo_count = min(wmo_pick_counts.get(int(r["wmo"]), 0) for r in avail)
            best_pool = [r for r in avail if wmo_pick_counts.get(int(r["wmo"]), 0) == min_wmo_count]
            best_pool.sort(key=lambda r: (r["date"], r["wmo"], r.get("cycle", 0)))
            chosen = rng.choice(best_pool)
            return chosen

        # Round 1: One profile per active space-time cell/slice
        for bid in all_bin_ids:
            if len(picked_rows) >= n_target:
                break
            chosen = _pick_best_from_bin(bins_dict[bid])
            if chosen is not None:
                picked_rows.append(chosen)
                used_indices.add(chosen.name)
                wmo_val = int(chosen["wmo"])
                wmo_pick_counts[wmo_val] = wmo_pick_counts.get(wmo_val, 0) + 1

        # Round 2: If we still need more picks to reach n_target
        while len(picked_rows) < n_target:
            progress_made = False
            for bid in all_bin_ids:
                if len(picked_rows) >= n_target:
                    break
                chosen = _pick_best_from_bin(bins_dict[bid])
                if chosen is not None:
                    picked_rows.append(chosen)
                    used_indices.add(chosen.name)
                    wmo_val = int(chosen["wmo"])
                    wmo_pick_counts[wmo_val] = wmo_pick_counts.get(wmo_val, 0) + 1
                    progress_made = True
            if not progress_made:
                break

        picked_rows.sort(key=lambda r: (r["date"], r["wmo"], r.get("cycle", 0)))
        picks = [_to_pick(r) for r in picked_rows]

        distinct_wmo_count = len(wmo_pick_counts)
        method_desc = (
            f"Space-time stratified grid selection ({len(picks)} profiles across "
            f"{n_t} time slices and {n_s} spatial cells, seed={seed}). "
            f"{distinct_wmo_count} distinct floats."
        )

        return SampleSelection(
            picks=picks,
            method=method_desc,
            seed=seed,
            n_available=n_avail,
            n_requested=n_requested,
            warning=warning,
        )


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


def select_sample(
    bbox_or_basin: Union[BoundingBox, tuple[float, float, float, float], list[float], str, Any, None] = None,
    date_range: Optional[Union[DateRange, tuple[Any, Any]]] = None,
    n: int = SAMPLE_DEFAULT,
    mode: Union[str, Any] = "research",
    fetch_key: str = "",
    seed: Optional[int] = None,
    index: Optional[FloatIndex] = None,
) -> SampleSelection:
    """Deterministically select n profiles spread evenly across space and time."""
    idx = index or load_float_index()
    return idx.select_sample(
        bbox_or_basin=bbox_or_basin,
        date_range=date_range,
        n=n,
        mode=mode,
        fetch_key=fetch_key,
        seed=seed,
    )
