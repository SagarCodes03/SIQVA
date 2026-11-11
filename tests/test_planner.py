"""Tests for layered validation and query planner (src/siqva/planner.py)."""

from datetime import date
from unittest.mock import MagicMock
import pandas as pd
import pytest

from siqva.capabilities import DataNeed, get_capability_profile
from siqva.floatindex import CoverageStatus, FloatIndex
from siqva.planner import (
    PlanDecision,
    PlanKind,
    PlanOption,
    get_levels_per_dbar,
    get_max_full_rows,
    plan_request,
)
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)
from siqva.validator import SpecValidationError, validate_structure


@pytest.fixture
def mock_index():
    """Create a mock FloatIndex with configurable query and count returns."""
    idx = MagicMock(spec=FloatIndex)
    idx.is_available = True
    idx.coverage_status.return_value = CoverageStatus.FULL
    idx.count_profiles.return_value = 10
    return idx


def test_structure_validation_hard_physical_constraints():
    """Verify validate_structure catches hard physical errors only."""
    valid_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-10"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        intent=Intent.PROFILE,
    )
    validate_structure(valid_spec)

    # Dates out of order
    with pytest.raises(SpecValidationError, match="Start date.*must be before"):
        invalid_dates = valid_spec.model_copy(
            update={"date_range": DateRange(start="2022-01-10", end="2022-01-01")}
        )
        validate_structure(invalid_dates)

    # Depth exceeds 2000 dbar
    with pytest.raises(SpecValidationError, match="cannot exceed 2000.0 dbar"):
        invalid_depth = valid_spec.model_copy(
            update={"depth_range": DepthRange(min_depth=0.0, max_depth=2500.0)}
        )
        validate_structure(invalid_depth)

    # Antimeridian without allow_antimeridian
    antimeridian_spec = valid_spec.model_copy(
        update={"region": BoundingBox(lon_min=170.0, lon_max=-170.0, lat_min=-5.0, lat_max=5.0)}
    )
    with pytest.raises(SpecValidationError, match="180° meridian"):
        validate_structure(antimeridian_spec, allow_antimeridian=False)

    # Antimeridian with allow_antimeridian passes
    validate_structure(antimeridian_spec, allow_antimeridian=True)


def test_structure_validation_basin_queries():
    """Verify basin queries without bounding boxes pass structure validation."""
    basin_spec = QuerySpec(
        basin="Pacific Ocean",
        date_range=DateRange(start="2022-01-01", end="2022-01-10"),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    assert basin_spec.region is None
    assert basin_spec.basin == "Pacific Ocean"
    validate_structure(basin_spec)

    # Invalid basin raises SpecValidationError
    invalid_basin = basin_spec.model_copy(update={"basin": "Unknown Basin"})
    with pytest.raises(SpecValidationError, match="Basin 'Unknown Basin' is not supported"):
        validate_structure(invalid_basin)


def test_metadata_request_branch_returns_full(mock_index):
    """Verify METADATA intent (Map) returns FULL using local float index with zero rows."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-10"),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )
    decision = plan_request(spec, index=mock_index)
    assert decision.plan == PlanKind.FULL
    assert decision.estimated_rows == 0
    assert decision.data_need == DataNeed.METADATA
    assert decision.profile_count_verified is True


def test_single_month_fitting_request_returns_full(mock_index):
    """Verify small request whose estimated rows fit max_full_rows returns FULL."""
    # 10 profiles * 500 dbar * 2 levels/dbar = 10,000 rows <= 60,000
    mock_index.count_profiles.return_value = 10

    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-15"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        intent=Intent.PROFILE,
    )
    decision = plan_request(spec, index=mock_index)
    assert decision.plan == PlanKind.FULL
    assert decision.profile_count == 10
    assert decision.estimated_rows == 10_000
    assert len(decision.reasons) > 0


def test_multi_month_fitting_chunks_returns_chunked(mock_index):
    """Verify multi-month request where each chunk fits max_full_rows returns CHUNKED."""
    # Each month returns 20 profiles -> 20,000 rows per month <= 60,000
    mock_index.count_profiles.return_value = 20

    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        intent=Intent.PROFILE,
    )
    decision = plan_request(spec, index=mock_index)
    assert decision.plan == PlanKind.CHUNKED
    assert len(decision.monthly_chunks) == 3
    assert all(c["estimated_rows"] <= get_max_full_rows() for c in decision.monthly_chunks)


def test_oversized_sample_ok_intent_returns_sample(mock_index):
    """Verify request exceeding chunk capacity for SAMPLE_OK intent returns SAMPLE."""
    # 200 profiles in each month -> 200 * 500 * 2 = 200,000 rows > 60,000 max_full_rows
    mock_index.count_profiles.return_value = 200

    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        intent=Intent.PROFILE,
    )
    decision = plan_request(spec, index=mock_index)
    assert decision.plan == PlanKind.SAMPLE
    assert decision.data_need == DataNeed.SAMPLE_OK
    assert len(decision.options) > 0


def test_oversized_full_required_intent_returns_refuse_with_working_options(mock_index):
    """Verify request exceeding capacity for FULL_REQUIRED intent returns REFUSE with options."""
    mock_index.count_profiles.return_value = 200

    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        intent=Intent.HOVMOLLER,
    )
    decision = plan_request(spec, index=mock_index)
    assert decision.plan == PlanKind.REFUSE
    assert decision.data_need == DataNeed.FULL_REQUIRED
    assert len(decision.options) >= 1
    # Check that every option builds a valid spec
    for opt in decision.options:
        assert isinstance(opt, PlanOption)
        validate_structure(opt.spec)


def test_antimeridian_box_handling(mock_index):
    """Verify antimeridian crossing box handling across METADATA, SAMPLE_OK, and FULL_REQUIRED."""
    spec_base = QuerySpec(
        region=BoundingBox(lon_min=170.0, lon_max=-170.0, lat_min=-5.0, lat_max=5.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-10"),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )

    # METADATA -> FULL
    dec_meta = plan_request(spec_base, index=mock_index)
    assert dec_meta.plan == PlanKind.FULL

    # SAMPLE_OK -> SAMPLE
    spec_prof = spec_base.model_copy(update={"intent": Intent.PROFILE})
    dec_prof = plan_request(spec_prof, index=mock_index)
    assert dec_prof.plan == PlanKind.SAMPLE

    # FULL_REQUIRED -> REFUSE with working options
    spec_hov = spec_base.model_copy(update={"intent": Intent.HOVMOLLER})
    dec_hov = plan_request(spec_hov, index=mock_index)
    assert dec_hov.plan == PlanKind.REFUSE
    assert len(dec_hov.options) > 0


def test_basin_query_handling(mock_index):
    """Verify whole basin queries across METADATA, SAMPLE_OK, and FULL_REQUIRED."""
    spec_basin = QuerySpec(
        basin="Pacific Ocean",
        date_range=DateRange(start="2022-01-01", end="2022-01-10"),
        variables=[Variable.TEMP],
        intent=Intent.MAP,
    )

    # METADATA -> FULL
    dec_meta = plan_request(spec_basin, index=mock_index)
    assert dec_meta.plan == PlanKind.FULL

    # SAMPLE_OK -> SAMPLE
    spec_sample = spec_basin.model_copy(update={"intent": Intent.PROFILE})
    dec_sample = plan_request(spec_sample, index=mock_index)
    assert dec_sample.plan == PlanKind.SAMPLE

    # FULL_REQUIRED -> REFUSE with gazetteer sub-regions
    spec_full = spec_basin.model_copy(update={"intent": Intent.CLIMATOLOGY})
    dec_full = plan_request(spec_full, index=mock_index)
    assert dec_full.plan == PlanKind.REFUSE
    sub_opts = [o for o in dec_full.options if o.option_type == "smaller_region"]
    assert len(sub_opts) > 0


def test_fallback_without_index():
    """Verify fallback when float index is unavailable uses geometric cost with unverified note."""
    empty_index = FloatIndex(df=None)
    assert empty_index.is_available is False

    # Small query fits cost limit
    small_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=62.0, lat_min=10.0, lat_max=12.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    dec_small = plan_request(small_spec, index=empty_index)
    assert dec_small.plan == PlanKind.FULL
    assert dec_small.is_fallback is True
    assert dec_small.profile_count_verified is False

    # Huge query exceeds cost limit
    large_spec = QuerySpec(
        region=BoundingBox(lon_min=50.0, lon_max=100.0, lat_min=-30.0, lat_max=20.0),
        date_range=DateRange(start="2022-01-01", end="2022-12-31"),
        variables=[Variable.TEMP],
        intent=Intent.HOVMOLLER,
    )
    dec_large = plan_request(large_spec, index=empty_index)
    assert dec_large.plan == PlanKind.REFUSE
    assert dec_large.is_fallback is True
    assert dec_large.profile_count_verified is False
    assert len(dec_large.options) > 0


@pytest.mark.parametrize(
    "region_bbox",
    [
        BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),       # Arabian Sea
        BoundingBox(lon_min=85.0, lon_max=90.0, lat_min=10.0, lat_max=15.0),       # Bay of Bengal
        BoundingBox(lon_min=-40.0, lon_max=-35.0, lat_min=30.0, lat_max=35.0),     # North Atlantic
        BoundingBox(lon_min=-110.0, lon_max=-105.0, lat_min=-5.0, lat_max=0.0),    # Equatorial Pacific
        BoundingBox(lon_min=70.0, lon_max=75.0, lat_min=-35.0, lat_max=-30.0),     # Southern Ocean
    ],
)
def test_parametrized_consistency_same_request_size(region_bbox, mock_index):
    """Verify that requests with the same profile count in different regions get identical decisions."""
    # When profile count is 15 across all regions, all get FULL
    mock_index.count_profiles.return_value = 15

    spec = QuerySpec(
        region=region_bbox,
        date_range=DateRange(start="2022-01-01", end="2022-01-14"),
        variables=[Variable.TEMP],
        intent=Intent.PROFILE,
    )
    decision = plan_request(spec, index=mock_index)
    assert decision.plan == PlanKind.FULL
    assert decision.profile_count == 15

