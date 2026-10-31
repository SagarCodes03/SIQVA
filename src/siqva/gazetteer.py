"""Gazetteer and spatial region resolution with fuzzy matching and coordinate parsing."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz

from .spec import BoundingBox


class RegionStatus(str, Enum):
    """Resolution status for a geographic query."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class RegionResolution(BaseModel):
    """Result of attempting to resolve a region string to a BoundingBox."""

    model_config = ConfigDict(frozen=True)

    status: RegionStatus
    region_name: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    score: float
    clarification_request: Optional[str] = None


# Approximate bounding boxes for standard oceanographic areas.
# NOTE: All bounding boxes below are approximate definitions, not official boundaries.
KNOWN_REGIONS: dict[str, BoundingBox] = {
    # Approximate definition for the Arabian Sea, not an official boundary
    "Arabian Sea": BoundingBox(lon_min=50.0, lon_max=77.0, lat_min=8.0, lat_max=25.0),
    # Approximate definition for the Bay of Bengal, not an official boundary
    "Bay of Bengal": BoundingBox(lon_min=80.0, lon_max=100.0, lat_min=5.0, lat_max=22.5),
    # Approximate definition for the Indian Ocean basin, not an official boundary
    "Indian Ocean": BoundingBox(lon_min=20.0, lon_max=120.0, lat_min=-50.0, lat_max=25.0),
    # Approximate definition for Eastern equatorial Pacific, not an official boundary.
    # Excludes the western half because the antimeridian isn't supported.
    "Eastern equatorial Pacific": BoundingBox(
        lon_min=-170.0, lon_max=-80.0, lat_min=-10.0, lat_max=10.0
    ),
    # Approximate definition for the North Atlantic, not an official boundary
    "North Atlantic": BoundingBox(lon_min=-80.0, lon_max=0.0, lat_min=0.0, lat_max=65.0),
    # Approximate definition for the Mediterranean Sea, not an official boundary
    "Mediterranean Sea": BoundingBox(lon_min=-6.0, lon_max=36.0, lat_min=30.0, lat_max=46.0),
}

# Alias dictionary mapping common variations to canonical region names
REGION_ALIASES: dict[str, str] = {
    # Arabian Sea
    "arabian sea": "Arabian Sea",
    "the arabian sea": "Arabian Sea",
    "arabian": "Arabian Sea",
    # Bay of Bengal
    "bay of bengal": "Bay of Bengal",
    "the bay of bengal": "Bay of Bengal",
    "bob": "Bay of Bengal",
    # Indian Ocean
    "indian ocean": "Indian Ocean",
    "the indian ocean": "Indian Ocean",
    # Eastern equatorial Pacific
    "eastern equatorial pacific": "Eastern equatorial Pacific",
    "the eastern equatorial pacific": "Eastern equatorial Pacific",
    "eastern equatorial pacific ocean": "Eastern equatorial Pacific",
    "equatorial pacific": "Eastern equatorial Pacific",
    "the equatorial pacific": "Eastern equatorial Pacific",
    "equatorial pacific ocean": "Eastern equatorial Pacific",
    "eq pac": "Eastern equatorial Pacific",
    # North Atlantic
    "north atlantic": "North Atlantic",
    "the north atlantic": "North Atlantic",
    "north atlantic ocean": "North Atlantic",
    # Mediterranean Sea
    "mediterranean sea": "Mediterranean Sea",
    "the mediterranean sea": "Mediterranean Sea",
    "mediterranean": "Mediterranean Sea",
    "med sea": "Mediterranean Sea",
}

# Compass / ocean word protection constants
_DIRECTIONS: dict[str, set[str]] = {
    "north": {"north", "northern"},
    "south": {"south", "southern"},
    "east": {"east", "eastern"},
    "west": {"west", "western"},
    "equatorial": {"equatorial"},
}
_ALL_DIRECTION_WORDS: set[str] = {w for group in _DIRECTIONS.values() for w in group}
_OCEAN_WORDS: set[str] = {"atlantic", "pacific", "indian", "arctic", "antarctic", "southern"}
_GENERIC_BODY_WORDS: set[str] = {"the", "of", "in", "sea", "ocean", "bay"}

# Region domain metadata for direction and ocean compatibility checking
_REGION_METADATA: dict[str, dict] = {
    "Arabian Sea": {
        "ocean": None,
        "directions": set(),
        "body_type": "sea",
        "substantive": {"arabian"},
    },
    "Bay of Bengal": {
        "ocean": None,
        "directions": set(),
        "body_type": "bay",
        "substantive": {"bengal"},
    },
    "Indian Ocean": {
        "ocean": "indian",
        "directions": set(),
        "body_type": "ocean",
        "substantive": {"indian"},
    },
    "Eastern equatorial Pacific": {
        "ocean": "pacific",
        "directions": {"east", "eastern", "equatorial"},
        "body_type": "ocean",
        "substantive": {"pacific"},
    },
    "North Atlantic": {
        "ocean": "atlantic",
        "directions": {"north", "northern"},
        "body_type": "ocean",
        "substantive": {"atlantic"},
    },
    "Mediterranean Sea": {
        "ocean": None,
        "directions": set(),
        "body_type": "sea",
        "substantive": {"mediterranean"},
    },
}

# Group all aliases under each canonical region for multi-alias fuzzy matching
_REGION_TO_ALIASES: dict[str, list[str]] = {name: [] for name in KNOWN_REGIONS}
for _alias, _canonical in REGION_ALIASES.items():
    if _canonical in _REGION_TO_ALIASES:
        _REGION_TO_ALIASES[_canonical].append(_alias)
for _canonical in KNOWN_REGIONS:
    if _canonical.lower() not in _REGION_TO_ALIASES[_canonical]:
        _REGION_TO_ALIASES[_canonical].append(_canonical.lower())


def _parse_coordinates(text: str) -> Optional[tuple[BoundingBox, str]]:
    """Attempt to parse coordinate bounding boxes like '10N-20N, 60E-70E'."""
    lat_pat = (
        r"(?P<lat1>-?\d+(?:\.\d+)?)\s*°?\s*(?P<lat1_dir>[NSns])?"
        r"\s*(?:-|to|\s+)\s*"
        r"(?P<lat2>-?\d+(?:\.\d+)?)\s*°?\s*(?P<lat2_dir>[NSns])?"
    )
    lon_pat = (
        r"(?P<lon1>-?\d+(?:\.\d+)?)\s*°?\s*(?P<lon1_dir>[EWew])?"
        r"\s*(?:-|to|\s+)\s*"
        r"(?P<lon2>-?\d+(?:\.\d+)?)\s*°?\s*(?P<lon2_dir>[EWew])?"
    )

    # 1. Lat then Lon
    m1 = re.search(rf"{lat_pat}\s*(?:,|\s+)\s*{lon_pat}", text, re.IGNORECASE)
    if m1:
        d = m1.groupdict()
        if d.get("lat1_dir") and d.get("lon1_dir"):
            lat1 = float(d["lat1"]) * (-1.0 if d["lat1_dir"].upper() == "S" else 1.0)
            lat2 = float(d["lat2"]) * (-1.0 if (d.get("lat2_dir") or d["lat1_dir"]).upper() == "S" else 1.0)
            lon1 = float(d["lon1"]) * (-1.0 if d["lon1_dir"].upper() == "W" else 1.0)
            lon2 = float(d["lon2"]) * (-1.0 if (d.get("lon2_dir") or d["lon1_dir"]).upper() == "W" else 1.0)
            lat_min, lat_max = min(lat1, lat2), max(lat1, lat2)
            lon_min, lon_max = min(lon1, lon2), max(lon1, lon2)
            if -90 <= lat_min <= lat_max <= 90 and -180 <= lon_min <= lon_max <= 180:
                bbox = BoundingBox(lon_min=lon_min, lon_max=lon_max, lat_min=lat_min, lat_max=lat_max)
                return bbox, m1.group(0).strip()

    # 2. Lon then Lat
    m2 = re.search(rf"{lon_pat}\s*(?:,|\s+)\s*{lat_pat}", text, re.IGNORECASE)
    if m2:
        d = m2.groupdict()
        if d.get("lon1_dir") and d.get("lat1_dir"):
            lon1 = float(d["lon1"]) * (-1.0 if d["lon1_dir"].upper() == "W" else 1.0)
            lon2 = float(d["lon2"]) * (-1.0 if (d.get("lon2_dir") or d["lon1_dir"]).upper() == "W" else 1.0)
            lat1 = float(d["lat1"]) * (-1.0 if d["lat1_dir"].upper() == "S" else 1.0)
            lat2 = float(d["lat2"]) * (-1.0 if (d.get("lat2_dir") or d["lat1_dir"]).upper() == "S" else 1.0)
            lat_min, lat_max = min(lat1, lat2), max(lat1, lat2)
            lon_min, lon_max = min(lon1, lon2), max(lon1, lon2)
            if -90 <= lat_min <= lat_max <= 90 and -180 <= lon_min <= lon_max <= 180:
                bbox = BoundingBox(lon_min=lon_min, lon_max=lon_max, lat_min=lat_min, lat_max=lat_max)
                return bbox, m2.group(0).strip()

    return None


def _is_candidate_compatible(query: str, canonical_name: str) -> bool:
    """Check direction, ocean, and substantive name word compatibility between query and candidate."""
    q_words = set(re.findall(r"\b[a-zA-Z]+\b", query.lower()))
    meta = _REGION_METADATA.get(canonical_name)
    if meta is None:
        return True

    # 1. Ocean basin check: query cannot specify a different ocean
    q_oceans = q_words & _OCEAN_WORDS
    if q_oceans:
        if meta["ocean"] not in q_oceans:
            return False

    # 2. Direction protection: if query specifies directions, candidate must support them
    if q_words & _DIRECTIONS["north"] and not (meta["directions"] & _DIRECTIONS["north"]):
        return False
    if q_words & _DIRECTIONS["south"] and not (meta["directions"] & _DIRECTIONS["south"]):
        return False
    if q_words & _DIRECTIONS["west"] and not (meta["directions"] & _DIRECTIONS["west"]):
        return False

    # 3. Explicit unknown bodies: Red Sea, North Sea
    if "red" in q_words and "sea" in q_words:
        return False
    if "north" in q_words and "sea" in q_words:
        return False

    # 4. Body type protection: sea vs ocean
    if "sea" in q_words and meta["body_type"] != "sea":
        return False
    if "ocean" in q_words and meta["body_type"] != "ocean":
        return False

    return True


def resolve_region(
    text: str,
    threshold: float = 75.0,
    ambiguity_margin: float = 5.0,
) -> RegionResolution:
    """Resolve natural-language region or coordinates to a BoundingBox.

    Follows a strict hierarchy:
    1. Coordinate strings (e.g. '10N-20N, 60E-70E') via regex.
    2. Exact name or known alias match.
    3. Fuzzy string matching via rapidfuzz above `threshold`, with compass/direction/ocean guards.

    Never guesses: if unknown or ambiguous, returns status with a clarification request
    and `bbox=None`.
    """
    raw_text = text.strip()
    available = ", ".join(KNOWN_REGIONS.keys())
    if not raw_text:
        return RegionResolution(
            status=RegionStatus.UNKNOWN,
            region_name=None,
            bbox=None,
            score=0.0,
            clarification_request=f"No region specified. Please specify one of: {available}, or provide coordinates.",
        )

    # 1. Look for coordinate strings
    coord_result = _parse_coordinates(raw_text)
    if coord_result is not None:
        bbox, matched_str = coord_result
        return RegionResolution(
            status=RegionStatus.RESOLVED,
            region_name=matched_str,
            bbox=bbox,
            score=100.0,
            clarification_request=None,
        )

    # Reject queries consisting purely of direction words or stopwords (e.g. "North", "in the North")
    q_words = set(re.findall(r"\b[a-zA-Z]+\b", raw_text.lower()))
    has_substantive = bool(q_words - _ALL_DIRECTION_WORDS - _GENERIC_BODY_WORDS)
    has_ocean_or_body = bool((q_words & _OCEAN_WORDS) or (q_words & {"sea", "bay", "ocean"}))
    if not has_substantive and not has_ocean_or_body:
        return RegionResolution(
            status=RegionStatus.UNKNOWN,
            region_name=None,
            bbox=None,
            score=0.0,
            clarification_request=(
                f"Unknown region '{raw_text}'. Supported regions are: {available}. "
                "Or specify coordinates like '10N-20N, 60E-70E'."
            ),
        )

    # 2. Exact or Alias match
    normalized = raw_text.lower()
    if normalized in REGION_ALIASES:
        canonical = REGION_ALIASES[normalized]
        return RegionResolution(
            status=RegionStatus.RESOLVED,
            region_name=canonical,
            bbox=KNOWN_REGIONS[canonical],
            score=100.0,
            clarification_request=None,
        )

    # Check exact match against canonical names (case-insensitive)
    for canonical, bbox in KNOWN_REGIONS.items():
        if canonical.lower() == normalized:
            return RegionResolution(
                status=RegionStatus.RESOLVED,
                region_name=canonical,
                bbox=bbox,
                score=100.0,
                clarification_request=None,
            )

    # 3. Fuzzy matching with rapidfuzz and direction/ocean protection
    normalized = raw_text.lower()
    if normalized in ("sea", "the sea"):
        candidates_str = "'Arabian Sea' or 'Mediterranean Sea'"
        return RegionResolution(
            status=RegionStatus.AMBIGUOUS,
            region_name=None,
            bbox=None,
            score=90.0,
            clarification_request=(
                f"Ambiguous region '{raw_text}'. Did you mean {candidates_str}? "
                "Please clarify your requested region."
            ),
        )

    region_scores: dict[str, float] = {}
    for canonical, aliases in _REGION_TO_ALIASES.items():
        if not _is_candidate_compatible(raw_text, canonical):
            continue
        best_for_region = max(fuzz.token_sort_ratio(normalized, alias) for alias in aliases)
        region_scores[canonical] = best_for_region

    if not region_scores:
        return RegionResolution(
            status=RegionStatus.UNKNOWN,
            region_name=None,
            bbox=None,
            score=0.0,
            clarification_request=(
                f"Unknown region '{raw_text}'. Supported regions are: {available}. "
                "Or specify coordinates like '10N-20N, 60E-70E'."
            ),
        )

    ranked = sorted(region_scores.items(), key=lambda item: item[1], reverse=True)
    best_name, best_score = ranked[0]

    if best_score < threshold:
        return RegionResolution(
            status=RegionStatus.UNKNOWN,
            region_name=None,
            bbox=None,
            score=round(best_score, 1),
            clarification_request=(
                f"Unknown region '{raw_text}'. Supported regions are: {available}. "
                "Or specify coordinates like '10N-20N, 60E-70E'."
            ),
        )

    # Check for ambiguous close matches
    close_matches = [
        name
        for name, score in ranked
        if score >= threshold and (best_score - score) <= ambiguity_margin
    ]

    if len(close_matches) > 1:
        candidates_str = " or ".join(f"'{m}'" for m in close_matches)
        return RegionResolution(
            status=RegionStatus.AMBIGUOUS,
            region_name=None,
            bbox=None,
            score=round(best_score, 1),
            clarification_request=(
                f"Ambiguous region '{raw_text}'. Did you mean {candidates_str}? "
                "Please clarify your requested region."
            ),
        )

    # Unambiguous winner above threshold
    return RegionResolution(
        status=RegionStatus.RESOLVED,
        region_name=best_name,
        bbox=KNOWN_REGIONS[best_name],
        score=round(best_score, 1),
        clarification_request=None,
    )
