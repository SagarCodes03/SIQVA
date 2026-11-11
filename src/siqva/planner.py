"""Layered query planning and validation for SIQVA.

Decides execution mode (FULL, CHUNKED, SAMPLE, REFUSE) deterministically from local
float index profile counts and module capability profiles rather than raw geometric cost.
One set of thresholds applies across all regions.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
import logging
import os
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from .capabilities import CapabilityProfile, DataNeed, get_capability_profile, resolve_effective_depth
from .chunking import get_max_chunks, get_max_total_rows, split_date_range_into_months
from .floatindex import (
    CoverageStatus,
    FloatIndex,
    _resolve_basin_code,
    load_float_index,
)
from .gazetteer import KNOWN_REGIONS
from .spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, QuerySpec
from .validator import DEFAULT_MAX_REQUEST_SIZE, SpecValidationError, validate_structure

logger = logging.getLogger(__name__)

# Maximum estimated observation rows for a single full fetch.
# Conservative unmeasured default derived from the largest cached fixture (~59,000 rows).
DEFAULT_MAX_FULL_ROWS: int = 60_000

# Estimated CTD observation records per decibar depth span.
# Empirical average derived from cached profiles in cache/ (core Argo ~1-2 levels/dbar).
DEFAULT_LEVELS_PER_DBAR: float = 2.0


def get_max_full_rows() -> int:
    """Return maximum allowable rows for a single FULL fetch."""
    val = os.getenv("SIQVA_MAX_FULL_ROWS")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MAX_FULL_ROWS


def get_levels_per_dbar() -> float:
    """Return estimated vertical CTD levels per decibar."""
    val = os.getenv("SIQVA_LEVELS_PER_DBAR")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return DEFAULT_LEVELS_PER_DBAR


class PlanKind(str, Enum):
    """Planner decision category."""

    FULL = "full"          # Fetch entire requested dataset directly
    CHUNKED = "chunked"    # Fetch entire dataset partitioned by calendar month
    SAMPLE = "sample"      # Visualize representative profile sample (for SAMPLE_OK modules)
    REFUSE = "refuse"      # Refuse execution with working options (for FULL_REQUIRED modules)


class PlanOption(BaseModel):
    """Structured, executable query modification providing a working path forward."""

    model_config = ConfigDict(frozen=True)

    label: str
    description: str = ""
    spec: QuerySpec
    option_type: str = ""  # narrow_period, shallower_depth, smaller_region, float_map, sample, run_full


class PlanDecision(BaseModel):
    """Deterministic planning result with capacity estimates and actionable alternatives."""

    model_config = ConfigDict(frozen=True)

    plan: PlanKind
    reasons: list[str] = Field(default_factory=list)
    options: list[PlanOption] = Field(default_factory=list)
    estimated_rows: int = 0
    profile_count: int = 0
    monthly_chunks: list[dict[str, Any]] = Field(default_factory=list)
    profile_count_verified: bool = True
    is_fallback: bool = False
    data_need: Optional[DataNeed] = None


def generate_plan_options(
    spec: QuerySpec,
    profile: CapabilityProfile,
    index: Optional[FloatIndex] = None,
    estimated_rows: int = 0,
    total_profiles: int = 0,
) -> list[PlanOption]:
    """Generate concrete, executable QuerySpec alternatives that will succeed under limits."""
    options: list[PlanOption] = []
    max_full_rows = get_max_full_rows()
    levels_per_dbar = get_levels_per_dbar()
    depth_range, _ = resolve_effective_depth(spec)
    depth_span = max(1.0, depth_range.max_depth - depth_range.min_depth) if depth_range else 500.0
    start_date = spec.date_range.start
    end_date = spec.date_range.end
    total_days = max(1, (end_date - start_date).days)
    target_loc = spec.basin or spec.region

    # 1. Narrower period option
    # Determine days fitting under max_full_rows
    if total_days > 7:
        if total_profiles > 0 and index and index.is_available:
            # Estimate allowable profiles
            allowable_profs = max(1, int(max_full_rows / (depth_span * levels_per_dbar)))
            # Try 7, 14, 30 days
            candidate_days = [7, 14, 30]
            chosen_end = None
            for d in candidate_days:
                if d < total_days:
                    c_end = start_date + timedelta(days=d)
                    c_cnt = index.count_profiles(target_loc, (start_date, c_end))
                    if (c_cnt * depth_span * levels_per_dbar) <= max_full_rows:
                        chosen_end = c_end
                        break
            if chosen_end is None and total_days > 14:
                chosen_end = start_date + timedelta(days=7)
        else:
            chosen_end = start_date + timedelta(days=min(7, total_days))

        if chosen_end and chosen_end <= end_date:
            narrowed_dates = DateRange(start=start_date, end=chosen_end)
            options.append(
                PlanOption(
                    label=f"Narrow period to {start_date} – {chosen_end}",
                    description=f"Limits query to {(chosen_end - start_date).days} days so data fits within memory limits.",
                    spec=spec.model_copy(update={"date_range": narrowed_dates}),
                    option_type="narrow_period",
                )
            )

    # 2. Shallower layer option
    if depth_span > 200.0:
        new_depth = DepthRange(min_depth=0.0, max_depth=200.0)
        options.append(
            PlanOption(
                label="Shallower depth (0–200 dbar)",
                description="Reduces vertical observation count to the upper ocean layer.",
                spec=spec.model_copy(update={"depth_range": new_depth}),
                option_type="shallower_depth",
            )
        )

    # 3. Smaller region (gazetteer sub-regions)
    sub_regions: list[tuple[str, BoundingBox]] = []
    if spec.basin:
        basin_code = _resolve_basin_code(spec.basin)
        if basin_code == "I":
            sub_regions = [
                ("Arabian Sea", KNOWN_REGIONS["Arabian Sea"]),
                ("Bay of Bengal", KNOWN_REGIONS["Bay of Bengal"]),
            ]
        elif basin_code == "P":
            sub_regions = [
                ("Nino 3.4", KNOWN_REGIONS["Nino 3.4"]),
                ("Nino 3", KNOWN_REGIONS["Nino 3"]),
                ("Eastern equatorial Pacific", KNOWN_REGIONS["Eastern equatorial Pacific"]),
            ]
        elif basin_code == "A":
            sub_regions = [
                ("North Atlantic", KNOWN_REGIONS["North Atlantic"]),
            ]
    elif spec.region:
        # Check known sub-regions whose bounding box is strictly within or overlaps spec.region
        r = spec.region
        if (r.lon_max - r.lon_min) * (r.lat_max - r.lat_min) > 500.0:
            for name, bbox in KNOWN_REGIONS.items():
                if name in ("Indian Ocean", "Southern Ocean"):
                    continue
                if bbox.lon_min >= r.lon_min and bbox.lon_max <= r.lon_max and bbox.lat_min >= r.lat_min and bbox.lat_max <= r.lat_max:
                    sub_regions.append((name, bbox))
                    if len(sub_regions) >= 2:
                        break

    for name, bbox in sub_regions:
        options.append(
            PlanOption(
                label=f"Sub-region: {name}",
                description=f"Focus query on the {name} sub-region.",
                spec=spec.model_copy(update={"region": bbox, "basin": None}),
                option_type="smaller_region",
            )
        )

    # 4. Float Position Map option (always succeeds via metadata)
    if spec.intent != Intent.MAP:
        options.append(
            PlanOption(
                label="View float position map",
                description="Inspects active float positions and cycles using metadata without downloading full profiles.",
                spec=spec.model_copy(update={"intent": Intent.MAP}),
                option_type="float_map",
            )
        )

    # 5. If module is FULL_REQUIRED, offer switching to individual profile sample
    if profile.data_need == DataNeed.FULL_REQUIRED and spec.intent != Intent.PROFILE:
        options.append(
            PlanOption(
                label="View profile sample (Temperature vs Depth)",
                description="Inspects individual sampled profiles rather than continuous regional statistics.",
                spec=spec.model_copy(update={"intent": Intent.PROFILE}),
                option_type="sample",
            )
        )

    return options


def plan_request(
    spec: QuerySpec,
    profile: Optional[CapabilityProfile] = None,
    index: Optional[FloatIndex] = None,
) -> PlanDecision:
    """Evaluate QuerySpec and produce a deterministic PlanDecision with capacity metrics.

    Args:
        spec: Validated QuerySpec (or candidate spec).
        profile: Optional CapabilityProfile (defaults to lookup for spec.intent).
        index: Optional FloatIndex instance (defaults to load_float_index()).

    Returns:
        PlanDecision containing plan kind (FULL, CHUNKED, SAMPLE, REFUSE), reasons,
        profile/row counts, and actionable options.
    """
    # 1. Structure check: hard physical constraints only (dates, coords, vars, 2000 dbar cap)
    validate_structure(spec, allow_antimeridian=True)

    # 2. Resolve capability profile and effective depth
    prof = profile or get_capability_profile(spec.intent)
    depth_range, _ = resolve_effective_depth(spec)
    depth_span = max(1.0, depth_range.max_depth - depth_range.min_depth) if depth_range else 500.0

    # 3. Resolve local float index
    idx = index if index is not None else load_float_index()

    # 4. Antimeridian Check (lon_min > lon_max)
    is_antimeridian = spec.region is not None and (spec.region.lon_min > spec.region.lon_max)
    if is_antimeridian:
        if prof.data_need == DataNeed.METADATA:
            cnt = idx.count_profiles(spec.region, spec.date_range) if idx.is_available else 0
            return PlanDecision(
                plan=PlanKind.FULL,
                reasons=["Metadata overview across the 180° antimeridian uses local float index only; no remote observations downloaded."],
                estimated_rows=0,
                profile_count=cnt,
                profile_count_verified=idx.is_available,
                data_need=prof.data_need,
            )
        elif prof.data_need == DataNeed.SAMPLE_OK:
            cnt = idx.count_profiles(spec.region, spec.date_range) if idx.is_available else 0
            opts = generate_plan_options(spec, prof, idx, estimated_rows=0, total_profiles=cnt)
            return PlanDecision(
                plan=PlanKind.SAMPLE,
                reasons=["Antimeridian bounding box (crossing 180°) visualized using a deterministic profile sample."],
                options=opts,
                estimated_rows=0,
                profile_count=cnt,
                profile_count_verified=idx.is_available,
                data_need=prof.data_need,
            )
        else:  # FULL_REQUIRED
            opts = generate_plan_options(spec, prof, idx, estimated_rows=0, total_profiles=0)
            return PlanDecision(
                plan=PlanKind.REFUSE,
                reasons=[
                    "Bounding boxes crossing the 180° meridian (antimeridian) where lon_min cannot be greater than lon_max "
                    "are not supported for full-dataset fetching. Please split the query into separate eastern and western boxes, "
                    "or select a non-crossing sub-region."
                ],
                options=opts,
                estimated_rows=0,
                profile_count=0,
                profile_count_verified=idx.is_available,
                data_need=prof.data_need,
            )

    # 5. Basin Queries (e.g. spec.basin is set, or ocean basin without bounding box)
    if spec.basin:
        if prof.data_need == DataNeed.METADATA:
            cnt = idx.count_profiles(spec.basin, spec.date_range) if idx.is_available else 0
            return PlanDecision(
                plan=PlanKind.FULL,
                reasons=[f"Metadata overview for {spec.basin} uses local float index only; no remote observations downloaded."],
                estimated_rows=0,
                profile_count=cnt,
                profile_count_verified=idx.is_available,
                data_need=prof.data_need,
            )
        elif prof.data_need == DataNeed.SAMPLE_OK:
            cnt = idx.count_profiles(spec.basin, spec.date_range) if idx.is_available else 0
            opts = generate_plan_options(spec, prof, idx, estimated_rows=0, total_profiles=cnt)
            return PlanDecision(
                plan=PlanKind.SAMPLE,
                reasons=[f"Ocean basin ({spec.basin}) observations visualized using a deterministic profile sample across the basin."],
                options=opts,
                estimated_rows=0,
                profile_count=cnt,
                profile_count_verified=idx.is_available,
                data_need=prof.data_need,
            )
        else:  # FULL_REQUIRED
            opts = generate_plan_options(spec, prof, idx, estimated_rows=0, total_profiles=0)
            return PlanDecision(
                plan=PlanKind.REFUSE,
                reasons=[
                    f"A full regional observation dataset or continuous diagram cannot be fetched for an entire ocean basin ({spec.basin}) in a single query; "
                    "a sample would not represent regional statistics."
                ],
                options=opts,
                estimated_rows=0,
                profile_count=0,
                profile_count_verified=idx.is_available,
                data_need=prof.data_need,
            )

    # 6. Metadata Requests (standard bbox)
    if prof.data_need == DataNeed.METADATA:
        cnt = idx.count_profiles(spec.region, spec.date_range) if idx.is_available else 0
        return PlanDecision(
            plan=PlanKind.FULL,
            reasons=["Metadata request uses local float index only; no observation rows downloaded."],
            estimated_rows=0,
            profile_count=cnt,
            profile_count_verified=idx.is_available,
            data_need=prof.data_need,
        )

    # 7. Observation Requests: Check Float Index Coverage
    target_loc = spec.basin or spec.region
    coverage = idx.coverage_status(spec.date_range) if (idx and idx.is_available) else CoverageStatus.NOT_COVERED

    # Fallback branch when index is unavailable or dates not covered
    if coverage == CoverageStatus.NOT_COVERED:
        area = (spec.region.lon_max - spec.region.lon_min) * (spec.region.lat_max - spec.region.lat_min) if spec.region else 1000.0
        days = max(1, (spec.date_range.end - spec.date_range.start).days)
        cost = area * days * (depth_span / 500.0)
        monthly_chunks = split_date_range_into_months(spec.date_range)
        max_chunks = get_max_chunks()

        if cost <= DEFAULT_MAX_REQUEST_SIZE:
            return PlanDecision(
                plan=PlanKind.FULL,
                reasons=["Float index coverage unavailable; geometric cost estimate fits single-request cap."],
                estimated_rows=int(cost * 4),
                profile_count=0,
                profile_count_verified=False,
                is_fallback=True,
                data_need=prof.data_need,
            )

        all_chunks_fit = len(monthly_chunks) <= max_chunks and all(
            (area * max(1, (c_dr.end - c_dr.start).days) * (depth_span / 500.0)) <= DEFAULT_MAX_REQUEST_SIZE
            for c_dr, _ in monthly_chunks
        )
        if all_chunks_fit:
            return PlanDecision(
                plan=PlanKind.CHUNKED,
                reasons=[f"Float index coverage unavailable; multi-month geometric cost fits {len(monthly_chunks)} monthly chunks."],
                estimated_rows=int(cost * 4),
                profile_count=0,
                profile_count_verified=False,
                is_fallback=True,
                data_need=prof.data_need,
            )

        # Exceeds cost cap
        opts = generate_plan_options(spec, prof, idx, estimated_rows=int(cost * 4), total_profiles=0)
        if prof.data_need == DataNeed.SAMPLE_OK:
            return PlanDecision(
                plan=PlanKind.SAMPLE,
                reasons=["Float index coverage unavailable; geometric cost exceeds limits; module permits profile sample."],
                options=opts,
                estimated_rows=int(cost * 4),
                profile_count=0,
                profile_count_verified=False,
                is_fallback=True,
                data_need=prof.data_need,
            )
        else:
            return PlanDecision(
                plan=PlanKind.REFUSE,
                reasons=["Float index coverage unavailable; request exceeds geometric cost limit and module requires complete data."],
                options=opts,
                estimated_rows=int(cost * 4),
                profile_count=0,
                profile_count_verified=False,
                is_fallback=True,
                data_need=prof.data_need,
            )

    # Primary Planner Branch: Exact profile counts from FloatIndex
    delayed_only = (spec.mode == DataMode.RESEARCH)
    total_profiles = idx.count_profiles(target_loc, date_range=spec.date_range, delayed_only=delayed_only)
    levels_per_dbar = get_levels_per_dbar()
    estimated_total_rows = int(total_profiles * depth_span * levels_per_dbar)

    monthly_chunks = split_date_range_into_months(spec.date_range)
    max_full_rows = get_max_full_rows()
    max_chunks = get_max_chunks()
    max_total_rows = get_max_total_rows()

    chunk_details: list[dict[str, Any]] = []
    all_chunks_fit = True
    for chunk_dr, label in monthly_chunks:
        c_profs = idx.count_profiles(target_loc, date_range=chunk_dr, delayed_only=delayed_only)
        c_rows = int(c_profs * depth_span * levels_per_dbar)
        chunk_details.append({
            "label": label,
            "date_range": chunk_dr,
            "profiles": c_profs,
            "estimated_rows": c_rows,
        })
        if c_rows > max_full_rows:
            all_chunks_fit = False

    # Branch A: Fits single FULL fetch
    if len(monthly_chunks) <= 1 and estimated_total_rows <= max_full_rows:
        return PlanDecision(
            plan=PlanKind.FULL,
            reasons=[f"Request fits full dataset limit ({estimated_total_rows:,} estimated rows <= {max_full_rows:,}; {total_profiles} profiles)."],
            estimated_rows=estimated_total_rows,
            profile_count=total_profiles,
            monthly_chunks=chunk_details,
            profile_count_verified=True,
            data_need=prof.data_need,
        )

    # Branch B: Fits CHUNKED fetch across calendar months
    if len(monthly_chunks) > 1 and len(monthly_chunks) <= max_chunks and estimated_total_rows <= max_total_rows and all_chunks_fit:
        return PlanDecision(
            plan=PlanKind.CHUNKED,
            reasons=[
                f"Request fits chunked fetch ({len(monthly_chunks)} monthly chunks <= {max_chunks}, "
                f"total {estimated_total_rows:,} estimated rows <= {max_total_rows:,}, every monthly chunk <= {max_full_rows:,} rows)."
            ],
            estimated_rows=estimated_total_rows,
            profile_count=total_profiles,
            monthly_chunks=chunk_details,
            profile_count_verified=True,
            data_need=prof.data_need,
        )

    # Branch C: Exceeds full/chunked capacity -> SAMPLE if module allows
    opts = generate_plan_options(spec, prof, idx, estimated_rows=estimated_total_rows, total_profiles=total_profiles)
    if prof.data_need == DataNeed.SAMPLE_OK:
        return PlanDecision(
            plan=PlanKind.SAMPLE,
            reasons=[
                f"Request exceeds full/chunked capacity ({estimated_total_rows:,} estimated rows, "
                f"{total_profiles} profiles across {len(monthly_chunks)} months). Visualized using a deterministic profile sample."
            ],
            options=opts,
            estimated_rows=estimated_total_rows,
            profile_count=total_profiles,
            monthly_chunks=chunk_details,
            profile_count_verified=True,
            data_need=prof.data_need,
        )

    # Branch D: Exceeds capacity and module is FULL_REQUIRED -> REFUSE with working options
    return PlanDecision(
        plan=PlanKind.REFUSE,
        reasons=[
            f"A region-wide statistic or continuous diagram needs all profiles ({estimated_total_rows:,} estimated rows "
            f"across {total_profiles} profiles exceeds limits); a sample would not represent it."
        ],
        options=opts,
        estimated_rows=estimated_total_rows,
        profile_count=total_profiles,
        monthly_chunks=chunk_details,
        profile_count_verified=True,
        data_need=prof.data_need,
    )

