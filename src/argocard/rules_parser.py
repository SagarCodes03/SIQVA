"""Deterministic rule-based parser extracting QuerySpec components from natural language."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Optional

import dateparser
from pydantic import BaseModel, ConfigDict, Field

from .gazetteer import (
    _ALL_DIRECTION_WORDS,
    _GENERIC_BODY_WORDS,
    _OCEAN_WORDS,
    RegionResolution,
    RegionStatus,
    resolve_region,
)
from .spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, Variable


class RulesParseResult(BaseModel):
    """Partial result object containing extracted spec components and missing/ambiguous lists."""

    model_config = ConfigDict(frozen=True)

    region: Optional[BoundingBox] = None
    region_name: Optional[str] = None
    date_range: Optional[DateRange] = None
    variables: Optional[list[Variable]] = None
    depth_range: Optional[DepthRange] = None
    mode: DataMode = DataMode.RESEARCH
    intent: Optional[Intent] = None
    missing: list[str] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)


# Variable synonym mapping
_VARIABLE_SYNONYMS: dict[str, Variable] = {
    "temperature": Variable.TEMP,
    "temp": Variable.TEMP,
    "warm": Variable.TEMP,
    "warmth": Variable.TEMP,
    # "sst" removed: differs from Argo subsurface temperature
    "salinity": Variable.PSAL,
    "salt": Variable.PSAL,
    "salty": Variable.PSAL,
    "saline": Variable.PSAL,
    "psu": Variable.PSAL,
    "pressure": Variable.PRES,
    "pressures": Variable.PRES,
    # "depth" is never mapped to PRES; PRES is only requested if explicitly "pressure"
}

# Mode keyword phrases (unambiguous phrases required; bare 'rt', 'expert', and 'operational' removed)
_STANDARD_MODE_PHRASES = [
    "near real-time",
    "near-real-time",
    "near real time",
    "real-time",
    "real time",
]
_EXPERT_MODE_PHRASES = [
    "include all data",
    "including all data",
    "including unchecked",
    "raw data",
]

# Month name regex
_MONTHS_PATTERN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
)


_PREPOSITIONS = {"in", "at", "near", "around", "for", "from", "to", "during", "of"}


def _strip_prepositions(text: str) -> str:
    """Strip leading and trailing sentence connective prepositions from an n-gram window."""
    tokens = text.strip().split()
    while tokens and tokens[0].lower() in _PREPOSITIONS:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in _PREPOSITIONS:
        tokens.pop()
    return " ".join(tokens)


def _extract_region(question: str) -> tuple[Optional[BoundingBox], Optional[str], Optional[str]]:
    """Scan the sentence for coordinate strings first, then n-gram windows.

    Returns:
        (bbox, region_name, ambiguous_note)
    """
    # 1. Scan for coordinates first across full string
    coord_res = resolve_region(question)
    if (
        coord_res.status == RegionStatus.RESOLVED
        and coord_res.region_name
        and any(d in coord_res.region_name for d in ("N", "S", "E", "W"))
    ):
        return coord_res.bbox, coord_res.region_name, None

    words = re.findall(r"\b[\w-]+\b", question)
    n_words = len(words)
    if n_words == 0:
        return None, None, None

    # Identify multi-word spans with direction/modifier + ocean/sea that must be kept intact
    # e.g. 'North Pacific', 'South Atlantic', 'Red Sea', 'North Sea'
    composite_spans: set[tuple[int, int]] = set()
    for i in range(n_words - 1):
        w1, w2 = words[i].lower(), words[i + 1].lower()
        if (w1 in _ALL_DIRECTION_WORDS or w1 == "red") and (
            w2 in _OCEAN_WORDS or w2 in {"sea", "ocean", "bay"}
        ):
            composite_spans.add((i, i + 1))
            if i + 2 < n_words:
                composite_spans.add((i, i + 2))

    matches: list[tuple[int, float, RegionResolution, str]] = []
    ambiguous_matches: list[RegionResolution] = []
    seen_windows: set[str] = set()

    # Check n-grams from length 5 down to 1
    for n in range(min(5, n_words), 0, -1):
        for i in range(n_words - n + 1):
            window = " ".join(words[i : i + n])
            cleaned = _strip_prepositions(window)
            if not cleaned or cleaned.lower() in seen_windows:
                continue
            seen_windows.add(cleaned.lower())

            # If cleaned is a single word that is a direction or generic stopword, skip
            if len(cleaned.split()) == 1:
                w_lower = cleaned.lower()
                if (
                    w_lower in _ALL_DIRECTION_WORDS
                    or w_lower in _GENERIC_BODY_WORDS
                    or w_lower in {"data", "show", "plot", "what", "is", "me"}
                ):
                    continue

            res = resolve_region(cleaned)
            if res.status == RegionStatus.RESOLVED:
                matches.append((len(cleaned.split()), res.score, res, cleaned))
            elif res.status == RegionStatus.AMBIGUOUS:
                ambiguous_matches.append(res)

    if matches:
        # Sort by window token length (descending) then similarity score (descending)
        matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
        best_res = matches[0][2]
        return best_res.bbox, best_res.region_name, None

    if ambiguous_matches:
        return None, None, ambiguous_matches[0].clarification_request

    return None, None, None


def _extract_date_range(text: str, today: date) -> Optional[DateRange]:
    """Extract date range using regex patterns and dateparser relative calculations."""
    base_dt = datetime(today.year, today.month, today.day)
    settings = {"RELATIVE_BASE": base_dt, "PREFER_DAY_OF_MONTH": "first"}

    # 1. 'last N days/weeks/months/years' or 'past N ...'
    m_rel = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|week|month|year)s?\b", text, re.IGNORECASE)
    if m_rel:
        num, unit = int(m_rel.group(1)), m_rel.group(2).lower()
        dt_start = dateparser.parse(f"{num} {unit}s ago", settings=settings)
        if dt_start:
            return DateRange(start=dt_start.date(), end=today)

    # 2. 'since <date>'
    m_since = re.search(
        rf"\bsince\s+({_MONTHS_PATTERN}\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{4}})\b",
        text,
        re.IGNORECASE,
    )
    if m_since:
        dt_start = dateparser.parse(m_since.group(1), settings=settings)
        if dt_start:
            return DateRange(start=dt_start.date(), end=today)

    # 3. YYYY-YYYY or YYYY to YYYY or between YYYY and YYYY
    m_yrange = re.search(
        r"\b(?:between\s+)?(20\d{2}|19\d{2})\s*(?:-|to|\sand\s)\s*(20\d{2}|19\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if m_yrange:
        y1, y2 = int(m_yrange.group(1)), int(m_yrange.group(2))
        return DateRange(start=date(min(y1, y2), 1, 1), end=date(max(y1, y2), 12, 31))

    # 4. Explicit ISO date range: YYYY-MM-DD to YYYY-MM-DD
    m_iso = re.search(
        r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|-|\sand\s)\s*(\d{4}-\d{2}-\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if m_iso:
        d1 = datetime.strptime(m_iso.group(1), "%Y-%m-%d").date()
        d2 = datetime.strptime(m_iso.group(2), "%Y-%m-%d").date()
        return DateRange(start=min(d1, d2), end=max(d1, d2))

    # 5. Month Year: e.g. 'March 2023'
    m_my = re.search(rf"\b({_MONTHS_PATTERN})\s+(20\d{{2}}|19\d{{2}})\b", text, re.IGNORECASE)
    if m_my:
        dt = dateparser.parse(m_my.group(0), settings=settings)
        if dt:
            y, m = dt.year, dt.month
            last_day = calendar.monthrange(y, m)[1]
            return DateRange(start=date(y, m, 1), end=date(y, m, last_day))

    # 6. Single year: 'in 2022' or 'for 2022' or 'during 2022'
    m_year = re.search(r"\b(?:in|during|for)\s+(20\d{2}|19\d{2})\b", text, re.IGNORECASE)
    if m_year:
        y = int(m_year.group(1))
        return DateRange(start=date(y, 1, 1), end=date(y, 12, 31))

    return None


def _extract_variables(text: str) -> Optional[list[Variable]]:
    """Extract physical variables from text using synonym dictionary.

    PRES is only extracted if 'pressure' or 'pressures' is explicitly mentioned.
    'depth' is never mapped to PRES.
    """
    lower = text.lower()
    # Mask out phrases where 'depth' is part of an intent phrase ('depth profile', 'at depth')
    clean_text = re.sub(r"\b(depth\s+profile|at\s+depth)\b", "", lower)
    words = re.findall(r"\b[a-zA-Z]+\b", clean_text)
    found: set[Variable] = set()
    for w in words:
        if w in _VARIABLE_SYNONYMS:
            found.add(_VARIABLE_SYNONYMS[w])

    if not found:
        return None
    # Sort deterministically
    return sorted(list(found), key=lambda v: v.value)


def _extract_mode(text: str) -> DataMode:
    """Extract Argo data mode; defaults to research unless explicit override phrases exist."""
    lower = text.lower()
    for phrase in _EXPERT_MODE_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", lower):
            return DataMode.EXPERT

    for phrase in _STANDARD_MODE_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", lower):
            return DataMode.STANDARD

    return DataMode.RESEARCH


def _extract_intent(text: str) -> tuple[Optional[Intent], Optional[str]]:
    """Extract user visualization/analysis intent based on keyword rules.

    Returns:
        (intent, conflict_note)
    """
    lower = text.lower()
    matched_intents: set[Intent] = set()

    # 1. T-S Diagram
    if any(
        re.search(rf"\b{re.escape(k)}\b", lower)
        for k in (
            "t-s",
            "ts diagram",
            "t-s diagram",
            "ts plot",
            "t-s plot",
            "temperature vs salinity",
            "salinity vs temperature",
            "temp vs psal",
        )
    ):
        matched_intents.add(Intent.TS)

    # 2. Trend
    if any(
        re.search(rf"\b{re.escape(k)}\b", lower)
        for k in (
            "trend",
            "over time",
            "time series",
            "warming trend",
            "cooling trend",
            "temporal change",
            "interannual",
        )
    ):
        matched_intents.add(Intent.TREND)

    # 3. Map
    if any(
        re.search(rf"\b{re.escape(k)}\b", lower)
        for k in (
            "map",
            "where",
            "nearest",
            "trajectory",
            "trajectories",
            "positions",
            "locations",
            "find floats",
            "locate floats",
        )
    ):
        matched_intents.add(Intent.MAP)

    # 4. Profile
    if any(
        re.search(rf"\b{re.escape(k)}\b", lower)
        for k in (
            "profile",
            "profiles",
            "vertical profile",
            "at depth",
            "depth profile",
            "cast",
        )
    ):
        matched_intents.add(Intent.PROFILE)

    if len(matched_intents) == 1:
        return list(matched_intents)[0], None

    if len(matched_intents) > 1:
        names = ", ".join(sorted(i.value for i in matched_intents))
        return None, f"Conflicting intent keywords detected: {names}"

    return None, None


def _extract_depth_range(text: str) -> Optional[DepthRange]:
    """Extract depth/pressure range if specified.

    Handles phrases like:
      - 'between 100 and 500 m', 'between 100m and 500m' -> DepthRange(100, 500)
      - 'top 500 m', 'top 500m', 'upper 200 dbar' -> DepthRange(0, 500)
      - 'below 1000 m', 'below 1000m', 'deeper than 1000 dbar' -> DepthRange(1000, 2000)
      - 'from 0 to 1000 dbar', '0-1000 dbar', '0 to 1000m' -> DepthRange(0, 1000)
      - 'down to 1000m', 'to 1500 dbar' -> DepthRange(0, 1500)
    """
    units = r"(?:m|meters|meter|dbar|decibars|decibar)"

    # 1. 'between X [unit] and Y <unit>'
    m_between = re.search(
        rf"\bbetween\s+(\d+(?:\.\d+)?)\s*(?:{units})?\s*(?:and|to|-)\s*(\d+(?:\.\d+)?)\s*{units}\b",
        text,
        re.IGNORECASE,
    )
    if m_between:
        d1, d2 = float(m_between.group(1)), float(m_between.group(2))
        return DepthRange(min_depth=min(d1, d2), max_depth=max(d1, d2))

    # 2. 'top 500 m', 'upper 200 dbar', 'surface to 500 m'
    m_top = re.search(
        rf"\b(?:top|upper|surface to)\s+(\d+(?:\.\d+)?)\s*{units}?\b",
        text,
        re.IGNORECASE,
    )
    if m_top:
        return DepthRange(min_depth=0.0, max_depth=float(m_top.group(1)))

    # 3. 'below 1000 m', 'deeper than 1000 dbar'
    # Oceanographic context: depths deeper than the threshold down to standard Argo 2000 dbar limit
    m_below = re.search(
        rf"\b(?:below|deeper than)\s+(\d+(?:\.\d+)?)\s*{units}\b",
        text,
        re.IGNORECASE,
    )
    if m_below:
        return DepthRange(min_depth=float(m_below.group(1)), max_depth=2000.0)

    # 4. 'from X [unit] to Y <unit>' or 'X-Y <unit>' or 'X to Y <unit>'
    m_range = re.search(
        rf"\b(?:from\s+)?(\d+(?:\.\d+)?)\s*(?:{units})?\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*{units}\b",
        text,
        re.IGNORECASE,
    )
    if m_range:
        d1, d2 = float(m_range.group(1)), float(m_range.group(2))
        return DepthRange(min_depth=min(d1, d2), max_depth=max(d1, d2))

    # 5. 'down to 1000m' or 'up to 1500 dbar' or 'to 1500 dbar'
    m_down = re.search(
        rf"\b(?:down to|up to|to)\s+(\d+(?:\.\d+)?)\s*{units}\b",
        text,
        re.IGNORECASE,
    )
    if m_down:
        return DepthRange(min_depth=0.0, max_depth=float(m_down.group(1)))

    return None


def parse_rules(question: str, today: Optional[date] = None) -> RulesParseResult:
    """Parse a natural-language Argo query into partial spec components with missing/ambiguous lists.

    Args:
        question: User query string.
        today: Reference date for relative temporal parsing (defaults to date.today()).

    Returns:
        RulesParseResult with extracted components, missing fields, and ambiguity notes.
    """
    if today is None:
        today = date.today()

    missing: list[str] = []
    ambiguous: list[str] = []

    # 1. Region
    bbox, region_name, reg_amb = _extract_region(question)
    if reg_amb:
        ambiguous.append(f"region ({reg_amb})")
    elif bbox is None:
        missing.append("region")

    # 2. Date range
    date_range = _extract_date_range(question, today)
    if date_range is None:
        lower_q = question.lower()
        bare_month = re.search(
            r"\b(?:january|february|march|april|june|july|august|september|october|november|december|"
            r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|\bMay\b|in\s+may|for\s+may|during\s+may)\b",
            question,
            re.IGNORECASE,
        )
        ambiguous_relative = re.search(
            r"\b(last month|this month|this year|last year|recent|recently)\b",
            lower_q,
        )
        if bare_month or ambiguous_relative:
            ambiguous.append(
                "date_range (ambiguous expression: requires explicit year or date range)"
            )
        else:
            missing.append("date_range")

    # 3. Variables
    variables = _extract_variables(question)
    if re.search(r"\bsst\b", question, re.IGNORECASE):
        ambiguous.append(
            "variables ('sst' differs from Argo subsurface temperature; Argo floats measure in-situ subsurface profile temperature, not satellite SST)"
        )
    if variables is None:
        missing.append("variables")

    # 4. Mode
    mode = _extract_mode(question)

    # 5. Intent
    intent, intent_conflict = _extract_intent(question)
    if intent_conflict:
        ambiguous.append(f"intent ({intent_conflict})")
    elif intent is None:
        missing.append("intent")

    # 6. Depth range (optional)
    depth_range = _extract_depth_range(question)

    return RulesParseResult(
        region=bbox,
        region_name=region_name,
        date_range=date_range,
        variables=variables,
        depth_range=depth_range,
        mode=mode,
        intent=intent,
        missing=missing,
        ambiguous=ambiguous,
    )
