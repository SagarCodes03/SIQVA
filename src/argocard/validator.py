"""Validation and size caps for ArgoCard QuerySpec instances."""

from __future__ import annotations

from typing import Optional

from .spec import DepthRange, QuerySpec, Variable

# Default threshold in cost units (normalized degree-day-depth units based on 500 dbar reference)
# Provisional value based on limited measurements (single region and period); should be revisited.
DEFAULT_MAX_REQUEST_SIZE: float = 15_000.0


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


def validate_spec(
    spec: QuerySpec,
    max_request_size: float = DEFAULT_MAX_REQUEST_SIZE,
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
            f"lon_min ({bbox.lon_min}) cannot be greater than lon_max ({bbox.lon_max})"
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

    if cost > max_request_size:
        suggestion = (
            f"Request volume ({cost:,.1f} cost units) exceeds the maximum limit ({max_request_size:,.1f}). "
            f"Current area is {area:,.1f}°² across {days} days with depth range {depth.min_depth:.0f}–{depth.max_depth:.0f} dbar. "
            "Please narrow your query by shrinking the bounding box (e.g. fewer degrees of latitude/longitude), "
            "narrowing the date range (e.g. fewer months or days), or choosing a shallower depth range."
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
