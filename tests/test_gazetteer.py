"""Tests for gazetteer resolution: coordinates, exact, alias, typos, ambiguity, unknown, and compass protection."""

import pytest

from argocard.gazetteer import (
    KNOWN_REGIONS,
    RegionResolution,
    RegionStatus,
    resolve_region,
)
from argocard.spec import BoundingBox


# 1. Exact matches
@pytest.mark.parametrize(
    "name",
    [
        "Arabian Sea",
        "Bay of Bengal",
        "Indian Ocean",
        "Eastern equatorial Pacific",
        "North Atlantic",
        "Mediterranean Sea",
    ],
)
def test_exact_matches(name: str):
    res = resolve_region(name)
    assert res.status == RegionStatus.RESOLVED
    assert res.region_name == name
    assert isinstance(res.bbox, BoundingBox)
    assert res.bbox == KNOWN_REGIONS[name]
    assert res.score == 100.0
    assert res.clarification_request is None


# 2. Alias matches
@pytest.mark.parametrize(
    "alias,expected_canonical",
    [
        ("arabian sea", "Arabian Sea"),
        ("the arabian sea", "Arabian Sea"),
        ("arabian", "Arabian Sea"),
        ("the bay of bengal", "Bay of Bengal"),
        ("bob", "Bay of Bengal"),
        ("the indian ocean", "Indian Ocean"),
        ("eastern equatorial pacific", "Eastern equatorial Pacific"),
        ("the eastern equatorial pacific", "Eastern equatorial Pacific"),
        ("equatorial pacific", "Eastern equatorial Pacific"),
        ("the equatorial pacific", "Eastern equatorial Pacific"),
        ("eq pac", "Eastern equatorial Pacific"),
        ("the north atlantic", "North Atlantic"),
        ("mediterranean", "Mediterranean Sea"),
        ("med sea", "Mediterranean Sea"),
        ("the mediterranean sea", "Mediterranean Sea"),
    ],
)
def test_alias_matches(alias: str, expected_canonical: str):
    res = resolve_region(alias)
    assert res.status == RegionStatus.RESOLVED
    assert res.region_name == expected_canonical
    assert res.bbox == KNOWN_REGIONS[expected_canonical]
    assert res.score == 100.0
    assert res.clarification_request is None


# 3. Typo fuzzy matches
@pytest.mark.parametrize(
    "typo,expected_canonical",
    [
        ("Arbian Sea", "Arabian Sea"),
        ("Bay of Bengall", "Bay of Bengal"),
        ("Indan Ocean", "Indian Ocean"),
        ("Eastern eqatorial Pacific", "Eastern equatorial Pacific"),
        ("Eqatorial Pacific", "Eastern equatorial Pacific"),
        ("North Atlantik", "North Atlantic"),
        ("Mediteranean Sea", "Mediterranean Sea"),
    ],
)
def test_typo_fuzzy_matches(typo: str, expected_canonical: str):
    res = resolve_region(typo)
    assert res.status == RegionStatus.RESOLVED
    assert res.region_name == expected_canonical
    assert res.bbox == KNOWN_REGIONS[expected_canonical]
    assert res.score >= 80.0
    assert res.clarification_request is None


# 4. Coordinate inputs
@pytest.mark.parametrize(
    "coord_str,expected_bbox",
    [
        ("10N-20N, 60E-70E", BoundingBox(lon_min=60.0, lon_max=70.0, lat_min=10.0, lat_max=20.0)),
        ("60E-70E, 10N-20N", BoundingBox(lon_min=60.0, lon_max=70.0, lat_min=10.0, lat_max=20.0)),
        ("10N to 20N, 30W to 10W", BoundingBox(lon_min=-30.0, lon_max=-10.0, lat_min=10.0, lat_max=20.0)),
        ("5S to 15N, 80E to 90E", BoundingBox(lon_min=80.0, lon_max=90.0, lat_min=-5.0, lat_max=15.0)),
        ("10°N-20°N, 60°E-70°E", BoundingBox(lon_min=60.0, lon_max=70.0, lat_min=10.0, lat_max=20.0)),
    ],
)
def test_coordinate_parsing(coord_str: str, expected_bbox: BoundingBox):
    res = resolve_region(coord_str)
    assert res.status == RegionStatus.RESOLVED
    assert res.bbox == expected_bbox
    assert res.score == 100.0
    assert res.clarification_request is None


# 5. Compass and ocean word protection (must return unknown)
@pytest.mark.parametrize(
    "unsupported_region",
    [
        "South Atlantic",
        "North Pacific",
        "South Pacific",
        "Southern Ocean",
        "Red Sea",
        "North Sea",
    ],
)
def test_compass_and_ocean_protection_returns_unknown(unsupported_region: str):
    res = resolve_region(unsupported_region)
    assert res.status == RegionStatus.UNKNOWN
    assert res.bbox is None
    assert res.region_name is None
    assert res.clarification_request is not None
    assert "Unknown region" in res.clarification_request
    assert "Supported regions are" in res.clarification_request


# 6. Ambiguous inputs (several close matches -> must not guess bbox)
@pytest.mark.parametrize(
    "ambiguous_input",
    [
        "Sea",
    ],
)
def test_ambiguous_inputs(ambiguous_input: str):
    res = resolve_region(ambiguous_input)
    assert res.status == RegionStatus.AMBIGUOUS
    assert res.bbox is None
    assert res.region_name is None
    assert res.clarification_request is not None
    assert "Ambiguous region" in res.clarification_request
    assert "Please clarify" in res.clarification_request


# 7. Other unknown inputs (score below threshold -> must not guess bbox)
@pytest.mark.parametrize(
    "unknown_input",
    [
        "Lake Tahoe",
        "Sahara Desert",
        "Mount Everest",
        "random xyz unknown",
        "",
    ],
)
def test_unknown_inputs(unknown_input: str):
    res = resolve_region(unknown_input)
    assert res.status == RegionStatus.UNKNOWN
    assert res.bbox is None
    assert res.region_name is None
    assert res.clarification_request is not None
    assert "Supported regions are" in res.clarification_request or "No region specified" in res.clarification_request
