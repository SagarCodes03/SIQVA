"""Tests for QuerySpec validator, bounds checking, and size caps."""

import re
import pytest

from argocard.spec import QuerySpec, Variable, Intent
from argocard.validator import (
    DEFAULT_MAX_REQUEST_SIZE,
    OversizedRequestError,
    SpecValidationError,
    validate_spec,
)


def test_valid_spec_passes_validation():
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-10"],
        variables=["TEMP", "PSAL"],
        depth_range=[0, 1000],
        intent=Intent.PROFILE,
    )
    # Should not raise
    validate_spec(spec)


@pytest.mark.parametrize(
    "bbox,err_substr",
    [
        ([-190, 70, 0, 10], "lon_min must be between -180 and 180"),
        ([60, 190, 0, 10], "lon_max must be between -180 and 180"),
        ([70, 60, 0, 10], "lon_min (70.0) cannot be greater than lon_max (60.0)"),
        ([60, 70, -95, 10], "lat_min must be between -90 and 90"),
        ([60, 70, 0, 95], "lat_max must be between -90 and 90"),
        ([60, 70, 20, 10], "lat_min (20.0) cannot be greater than lat_max (10.0)"),
    ],
)
def test_invalid_bbox_ranges(bbox, err_substr):
    spec = QuerySpec(
        region=bbox,
        date_range=["2023-01-01", "2023-01-10"],
        variables=["TEMP"],
        intent=Intent.MAP,
    )
    with pytest.raises(SpecValidationError, match=re.escape(err_substr)):
        validate_spec(spec)


def test_start_after_end_date():
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-02-01", "2023-01-01"],  # start after end
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    with pytest.raises(SpecValidationError, match="Start date .* must be before or equal to end date"):
        validate_spec(spec)


def test_invalid_depth_range():
    spec1 = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-10"],
        variables=["TEMP"],
        depth_range=[-10, 500],
        intent=Intent.PROFILE,
    )
    with pytest.raises(SpecValidationError, match="min_depth must be >= 0"):
        validate_spec(spec1)

    spec2 = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-10"],
        variables=["TEMP"],
        depth_range=[500, 100],
        intent=Intent.PROFILE,
    )
    with pytest.raises(SpecValidationError, match="min_depth .* cannot exceed max_depth"):
        validate_spec(spec2)


def test_oversized_request_triggers_error_with_suggestion():
    # Area: 60 deg * 40 deg = 2400 sq deg
    # Days: 365 days
    # Size: 2400 * 365 = 876,000 degree-days (exceeds default 100,000)
    spec = QuerySpec(
        region=[20.0, 80.0, -10.0, 30.0],
        date_range=["2022-01-01", "2023-01-01"],
        variables=["TEMP"],
        intent=Intent.MAP,
    )
    with pytest.raises(OversizedRequestError) as exc_info:
        validate_spec(spec, max_request_size=DEFAULT_MAX_REQUEST_SIZE)

    err = exc_info.value
    assert err.size > DEFAULT_MAX_REQUEST_SIZE
    assert "Please narrow your query" in err.suggestion
    assert "shrinking the bounding box" in err.suggestion
    assert "narrowing the date range" in err.suggestion


def test_custom_max_request_size():
    # Small request: 5 deg * 5 deg = 25 sq deg over 10 days = 250 degree-days
    spec = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-11"],
        variables=["TEMP"],
        intent=Intent.MAP,
    )
    # Passes with normal cap
    validate_spec(spec, max_request_size=1000.0)

    # Fails when threshold is set lower than 250
    with pytest.raises(OversizedRequestError):
        validate_spec(spec, max_request_size=200.0)


def test_cost_estimate_scales_with_depth_range():
    """Cost estimate scales with depth range relative to 500 dbar baseline."""
    # 5 deg * 5 deg = 25 sq deg, 10 days
    # Baseline 0-500 dbar: cost = 25 * 10 * (500/500) = 250
    spec_500 = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-11"],
        variables=["TEMP"],
        depth_range=[0, 500],
        intent=Intent.MAP,
    )
    # Passes at cap=300
    validate_spec(spec_500, max_request_size=300.0)

    # Full depth 0-2000 dbar: cost = 25 * 10 * (2000/500) = 1000
    spec_2000 = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-11"],
        variables=["TEMP"],
        depth_range=[0, 2000],
        intent=Intent.MAP,
    )
    # Fails at cap=500 because cost is 1000
    with pytest.raises(OversizedRequestError) as exc_info:
        validate_spec(spec_2000, max_request_size=500.0)
    assert exc_info.value.size == 1000.0
    assert "shallower depth range" in exc_info.value.suggestion


def test_validator_defaults_depth_range_when_none():
    """When spec.depth_range is None, validator defaults to 0-500 dbar (depth_factor=1.0)."""
    spec_none = QuerySpec(
        region=[60.0, 65.0, 10.0, 15.0],
        date_range=["2023-01-01", "2023-01-11"],
        variables=["TEMP"],
        intent=Intent.MAP,
    )
    assert spec_none.depth_range is None

    # Cost is 25 * 10 * 1.0 = 250.0
    validate_spec(spec_none, max_request_size=300.0)

    with pytest.raises(OversizedRequestError) as exc_info:
        validate_spec(spec_none, max_request_size=200.0)
    assert exc_info.value.size == 250.0
