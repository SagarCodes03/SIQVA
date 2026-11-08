"""Validation and size caps for SIQVA QuerySpec instances."""

from __future__ import annotations

import os
from typing import Optional

from .spec import DepthRange, QuerySpec, Variable

# Default threshold in cost units (normalized degree-day-depth units based on 500 dbar reference)
# Provisional value based on limited measurements (single region and period); should be revisited.
DEFAULT_MAX_REQUEST_SIZE: float = 15_000.0


def is_size_guardrail_enabled() -> bool:
    """Check whether size cap guardrail is active.

    Can be bypassed via environment variable SIQVA_DISABLE_SIZE_GUARDRAIL=1.
    """
    return os.getenv("SIQVA_DISABLE_SIZE_GUARDRAIL", "").lower() not in ("1", "true", "yes")


class SpecValidationError(ValueError):
    """Raised when a QuerySpec violates physical or domain constraints."""

    pass


class OversizedRequestError(SpecValidationError):
    """Raised when a request exceeds allowable size caps, providing narrowing advice."""

    def __init__(
        self,
        message: str,
        area: float,
        days: int,
        size: float,
        max_size: float,
        suggestion: str,
        depth_span: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.area = area
        self.days = days
        self.size = size
        self.max_size = max_size
        self.suggestion = suggestion
        self.depth_span = depth_span


def format_oversized_suggestion(
    area: float,
    days: int,
    depth_span: float,
    cost: float,
    max_request_size: float = DEFAULT_MAX_REQUEST_SIZE,
    region_name: Optional[str] = None,
    min_depth: float = 0.0,
    max_depth: float = 500.0,
) -> str:
    """Pure function generating actionable narrowing guidance from concrete numerical constraints."""
    reg_label = f"region '{region_name}' ({area:,.1f}°²)" if region_name else f"area {area:,.1f}°²"
    depth_factor = depth_span / 500.0
    cost_per_day = area * depth_factor
    max_days_at_depth = max(1, int(max_request_size / cost_per_day)) if cost_per_day > 0 else 1

    # Max depth span for requested days
    target_depth_span = (max_request_size / (area * days)) * 500.0 if (area * days) > 0 else 0.0

    lines = [
        f"Request volume ({cost:,.1f} cost units) exceeds the maximum limit ({max_request_size:,.1f}).",
        f"Current {reg_label} across {days} days with depth range {min_depth:.0f}–{max_depth:.0f} dbar (span {depth_span:.0f} dbar).",
        f"At this depth range, at most {max_days_at_depth} days fit under the limit.",
        "Please narrow your query with one of the following:",
        f"1. Shorter period: narrowing the date range to {max_days_at_depth} days or fewer (e.g. at most {max_days_at_depth} days at this depth).",
    ]
    if target_depth_span >= 10.0:
        lines.append(
            f"2. Shallower depth: choosing a shallower depth range with a span of at most {int(target_depth_span)} dbar (e.g. {min_depth:.0f}–{min_depth + int(target_depth_span):.0f} dbar) for {days} days."
        )
    else:
        lines.append(
            "2. Shallower depth: choosing a shallower depth range (e.g. surface layer 0–10 dbar) combined with a shorter period."
        )
    lines.append(
        f"3. Smaller region: shrinking the bounding box or specifying precise coordinates to reduce the area from {area:,.1f}°²."
    )
    return " ".join(lines)


def validate_spec(
    spec: QuerySpec,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
    allow_chunking: bool = False,
) -> None:
    """Validate bounds, temporal order, variables, depth range, and size caps of a QuerySpec.

    Computes a cost estimate incorporating geographic area, temporal duration, and depth range
    (defaulting to 0-500 dbar when no depth range is specified in the spec).

    Raises:
        SpecValidationError: If geographic, temporal, variable, or depth values are invalid.
        OversizedRequestError: If total query cost exceeds max_request_size.
    """
    bbox = spec.region

    # 1. Bounding box coordinates validation
    if not (-180.0 <= bbox.lon_min <= 180.0):
        raise SpecValidationError(
            f"lon_min must be between -180 and 180, got {bbox.lon_min}"
        )
    if not (-180.0 <= bbox.lon_max <= 180.0):
        raise SpecValidationError(
            f"lon_max must be between -180 and 180, got {bbox.lon_max}"
        )
    if bbox.lon_min > bbox.lon_max:
        raise SpecValidationError(
            f"Bounding boxes crossing the 180° meridian (antimeridian) where lon_min ({bbox.lon_min}) cannot be greater than lon_max ({bbox.lon_max}) "
            "are not supported. Please split the query into separate eastern and western boxes, or choose a region that does not cross 180°."
        )

    if not (-90.0 <= bbox.lat_min <= 90.0):
        raise SpecValidationError(
            f"lat_min must be between -90 and 90, got {bbox.lat_min}"
        )
    if not (-90.0 <= bbox.lat_max <= 90.0):
        raise SpecValidationError(
            f"lat_max must be between -90 and 90, got {bbox.lat_max}"
        )
    if bbox.lat_min > bbox.lat_max:
        raise SpecValidationError(
            f"lat_min ({bbox.lat_min}) cannot be greater than lat_max ({bbox.lat_max})"
        )

    # 2. Date range order validation
    start_date = spec.date_range.start
    end_date = spec.date_range.end
    if start_date > end_date:
        raise SpecValidationError(
            f"Start date ({start_date}) must be before or equal to end date ({end_date})"
        )

    # 3. Variables validation
    if not spec.variables:
        raise SpecValidationError("QuerySpec must contain at least one variable")

    for var in spec.variables:
        if not isinstance(var, Variable):
            raise SpecValidationError(
                f"Variable '{var}' is not an allowed variable. Allowed: {[v.value for v in Variable]}"
            )

    # 4. Depth range validation (defaults to 0-500 dbar when none specified)
    depth = spec.depth_range or DepthRange(min_depth=0.0, max_depth=500.0)
    if depth.min_depth < 0:
        raise SpecValidationError(
            f"min_depth must be >= 0, got {depth.min_depth}"
        )
    if depth.min_depth > depth.max_depth:
        raise SpecValidationError(
            f"min_depth ({depth.min_depth}) cannot exceed max_depth ({depth.max_depth})"
        )

    # 5. Cost estimate validation incorporating depth range
    area = (bbox.lon_max - bbox.lon_min) * (bbox.lat_max - bbox.lat_min)
    days = max(1, (end_date - start_date).days)
    depth_span = max(1.0, depth.max_depth - depth.min_depth)
    # Reference depth scale is 500 dbar; full 2000 dbar depth scales cost by 4x
    depth_factor = depth_span / 500.0
    cost = area * days * depth_factor

    if is_size_guardrail_enabled() and max_request_size is not None and cost > max_request_size:
        if allow_chunking:
            from .chunking import validate_chunkable_spec

            if validate_chunkable_spec(spec, max_request_size=max_request_size):
                return

        from .gazetteer import KNOWN_REGIONS

        region_name = next(
            (name for name, b in KNOWN_REGIONS.items() if b == bbox),
            None,
        )
        suggestion = format_oversized_suggestion(
            area=area,
            days=days,
            depth_span=depth_span,
            cost=cost,
            max_request_size=max_request_size,
            region_name=region_name,
            min_depth=depth.min_depth,
            max_depth=depth.max_depth,
        )
        raise OversizedRequestError(
            message=suggestion,
            area=area,
            days=days,
            size=cost,
            max_size=max_request_size,
            suggestion=suggestion,
            depth_span=depth_span,
        )
