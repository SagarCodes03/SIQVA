"""Tests for capability profiles (src/siqva/capabilities.py) and 2000 dbar depth limit."""

import pytest

from siqva.capabilities import (
    CAPABILITY_PROFILES,
    DataNeed,
    get_capability_profile,
    resolve_effective_depth,
)
from siqva.parser import parse_detailed
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)
from siqva.validator import SpecValidationError, validate_spec


def test_every_intent_has_capability_profile():
    """Verify that every Intent enum member has a registered CapabilityProfile."""
    for intent in Intent:
        assert intent in CAPABILITY_PROFILES
        prof = get_capability_profile(intent)
        assert prof.intent == intent
        assert isinstance(prof.data_need, DataNeed)
        assert prof.label != ""


def test_defaults_per_intent():
    """Verify default depths and data needs per Intent."""
    # Map intent
    map_prof = get_capability_profile(Intent.MAP)
    assert map_prof.data_need == DataNeed.METADATA
    assert map_prof.default_depth is None
    assert map_prof.per_profile_only is False

    # Acoustic intent needs 2000 dbar
    ac_prof = get_capability_profile(Intent.ACOUSTIC)
    assert ac_prof.data_need == DataNeed.SAMPLE_OK
    assert ac_prof.default_depth == DepthRange(min_depth=0.0, max_depth=2000.0)
    assert ac_prof.per_profile_only is True

    # Drift velocity intent
    drift_prof = get_capability_profile(Intent.DRIFT)
    assert drift_prof.data_need == DataNeed.FULL_REQUIRED
    assert drift_prof.default_depth == DepthRange(min_depth=0.0, max_depth=20.0)

    # Climatology & Hovmoller
    clim_prof = get_capability_profile(Intent.CLIMATOLOGY)
    assert clim_prof.data_need == DataNeed.FULL_REQUIRED
    assert clim_prof.default_depth == DepthRange(min_depth=0.0, max_depth=500.0)

    hov_prof = get_capability_profile(Intent.HOVMOLLER)
    assert hov_prof.data_need == DataNeed.FULL_REQUIRED
    assert hov_prof.default_depth == DepthRange(min_depth=0.0, max_depth=500.0)

    # Standard profile & physics
    prof_prof = get_capability_profile(Intent.PROFILE)
    assert prof_prof.data_need == DataNeed.SAMPLE_OK
    assert prof_prof.default_depth == DepthRange(min_depth=0.0, max_depth=500.0)

    omz_prof = get_capability_profile(Intent.OMZ)
    assert omz_prof.data_need == DataNeed.SAMPLE_OK
    assert omz_prof.default_depth == DepthRange(min_depth=0.0, max_depth=500.0)
    assert omz_prof.per_profile_only is True


def test_user_depth_always_wins():
    """Verify resolve_effective_depth prioritizes explicit user depth over intent defaults."""
    custom_depth = DepthRange(min_depth=50.0, max_depth=300.0)

    # Acoustic with user depth
    spec_acoustic = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=custom_depth,
        intent=Intent.ACOUSTIC,
    )
    depth, is_default = resolve_effective_depth(spec_acoustic)
    assert depth == custom_depth
    assert is_default is False

    # Acoustic without user depth -> gets 2000 dbar default
    spec_no_depth = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=None,
        intent=Intent.ACOUSTIC,
    )
    depth_def, is_def = resolve_effective_depth(spec_no_depth)
    assert depth_def == DepthRange(min_depth=0.0, max_depth=2000.0)
    assert is_def is True

    # Map without user depth -> gets None default
    spec_map_no_depth = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        depth_range=None,
        intent=Intent.MAP,
    )
    depth_map, is_def_map = resolve_effective_depth(spec_map_no_depth)
    assert depth_map is None
    assert is_def_map is True

    # Map with user depth -> user depth wins
    spec_map_with_depth = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=100.0),
        intent=Intent.MAP,
    )
    depth_map_u, is_def_map_u = resolve_effective_depth(spec_map_with_depth)
    assert depth_map_u == DepthRange(min_depth=0.0, max_depth=100.0)
    assert is_def_map_u is False


def test_depth_max_2000_dbar_enforced_by_validator():
    """Verify structure checks enforce maximum 2000 dbar core Argo limit."""
    valid_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        intent=Intent.PROFILE,
    )
    # 2000 dbar passes
    validate_spec(valid_spec, max_request_size=None)

    # 2001 dbar raises SpecValidationError
    invalid_spec = valid_spec.model_copy(
        update={"depth_range": DepthRange(min_depth=0.0, max_depth=2001.0)}
    )
    with pytest.raises(SpecValidationError, match="cannot exceed 2000.0 dbar"):
        validate_spec(invalid_spec, max_request_size=None)
