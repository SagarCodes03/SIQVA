"""templates.py
Safe, schema-validated query templates for FloatAI.

Responsibilities:
- Define supported query types (the 10 templates below)
- Define required / optional parameters per template
- Validate and sanitize parameters extracted by intent.py
- Convert them into a canonical, argopy-ready dict for fetcher.py

This module DOES NOT:
- Call argopy
- Call Ollama
- Fetch data
- Generate answers

Canonical output keys (only these ever leave this module):
  wmo, cycle, lat_min, lat_max, lon_min, lon_max,
  depth_min, depth_max, start_date, end_date, parameter
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

_NULL_STRINGS = {"", "none", "null", "n/a", "na", "nan"}
_BOX_KEYS = ["lat_min", "lat_max", "lon_min", "lon_max"]
_PARAM_ALIASES = {
    "temp": "TEMP", "temperature": "TEMP",
    "sal": "PSAL", "salinity": "PSAL", "psal": "PSAL",
    "pres": "PRES", "pressure": "PRES",
}


class MissingParametersError(ValueError):
    """Raised when required params are missing. intent.py can catch this
    and ask the user a clarification question using `.missing`."""

    def __init__(self, template: str, missing: List[str]):
        self.template = template
        self.missing = missing
        super().__init__(
            f"Missing required parameters for '{template}': {', '.join(missing)}"
        )


# ============================================================
# Sanitizing helpers
# ============================================================

def _is_null(value: Any) -> bool:
    """LLMs often return None, '', 'null', 'N/A' for 'not found'."""
    return value is None or (
        isinstance(value, str) and value.strip().lower() in _NULL_STRINGS
    )


def _num(key: str, value: Any, lo: float, hi: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number, got {value!r}")
    if not lo <= x <= hi:  # also rejects NaN
        raise ValueError(f"'{key}' out of range [{lo}, {hi}]: {x}")
    return x


def _wmo(value: Any) -> int:
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not (s.isdigit() and len(s) == 7):
        raise ValueError(f"Invalid WMO platform number (expected 7 digits): {value!r}")
    return int(s)


def _cycle(value: Any) -> int:
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid cycle number: {value!r}")
    if f != int(f) or f < 0:
        raise ValueError(f"Invalid cycle number: {value!r}")
    return int(f)


def _date(key: str, value: Any, end: bool = False) -> date:
    """Accepts date/datetime or 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY'.
    Partial dates expand to first day (start) or last day (end) of the period."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if end and fmt == "%Y-%m":
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1)
        elif end and fmt == "%Y":
            d = date(d.year + 1, 1, 1) - timedelta(days=1)
        return d
    raise ValueError(f"'{key}' must look like YYYY-MM-DD, got {value!r}")


def _parameter(value: Any) -> str:
    key = str(value).strip().lower()
    if key not in _PARAM_ALIASES:
        raise ValueError(
            f"Unsupported parameter {value!r}. Use one of: temperature, salinity, pressure"
        )
    return _PARAM_ALIASES[key]


# ============================================================
# Template definition
# ============================================================

@dataclass
class QueryTemplate:
    name: str
    description: str
    fetch_mode: str                      # 'region' | 'float' | 'profile'
    required_params: List[str]
    optional_params: List[str] = field(default_factory=list)
    target_chart: str = "line"           # 'line' | 'map' | 'time_series' | 'ts_diagram'
    depth_mode: str = "up_to"            # 'up_to' -> 0..depth, 'slice' -> depth +/- tolerance
    default_parameter: Optional[str] = None

    @property
    def allowed_params(self) -> List[str]:
        """Inputs accepted by this template (derived, so it can't drift)."""
        return self.required_params + self.optional_params

    # ---------------- validation ----------------

    def validate(self, params: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """(True, []) if all required params are present, else (False, missing)."""
        p = {k: v for k, v in params.items() if not _is_null(v)}
        missing = []
        for key in self.required_params:
            if key in p:
                continue
            # Region templates also accept an explicit bounding box
            if self.fetch_mode == "region" and key == "lat" and {"lat_min", "lat_max"} <= p.keys():
                continue
            if self.fetch_mode == "region" and key == "lon" and {"lon_min", "lon_max"} <= p.keys():
                continue
            missing.append(key)
        return len(missing) == 0, missing

    # ---------------- build ----------------

    def build_params(
        self,
        params: Dict[str, Any],
        radius_deg: float = 1.0,
        date_window_days: int = 15,
        depth_tol: float = 10.0,
    ) -> Dict[str, Any]:
        """Validate, sanitize and normalize params into the canonical dict.

        - Drops params this template doesn't allow (stops LLM hallucinated keys)
        - Point + radius -> bounding box (region templates)
        - Single 'date' -> start_date/end_date window (Argo floats only profile
          every ~10 days, so an exact day would usually return nothing)
        - 'depth' -> depth_min/depth_max
        """
        p = {k: v for k, v in params.items() if not _is_null(v)}
        ok, missing = self.validate(p)
        if not ok:
            raise MissingParametersError(self.name, missing)

        accepted = set(self.allowed_params)
        if self.fetch_mode == "region":
            accepted |= set(_BOX_KEYS)
        p = {k: v for k, v in p.items() if k in accepted}

        out: Dict[str, Any] = {}

        # identifiers
        if "wmo" in p:
            out["wmo"] = _wmo(p["wmo"])
        if "cycle" in p:
            out["cycle"] = _cycle(p["cycle"])

        # geography (region templates)
        if self.fetch_mode == "region":
            if {"lat_min", "lat_max"} <= p.keys():
                out["lat_min"] = _num("lat_min", p["lat_min"], -90, 90)
                out["lat_max"] = _num("lat_max", p["lat_max"], -90, 90)
            else:
                lat = _num("lat", p["lat"], -90, 90)
                out["lat_min"] = max(-90.0, lat - radius_deg)
                out["lat_max"] = min(90.0, lat + radius_deg)

            if {"lon_min", "lon_max"} <= p.keys():
                out["lon_min"] = _num("lon_min", p["lon_min"], -180, 180)
                out["lon_max"] = _num("lon_max", p["lon_max"], -180, 180)
            else:
                lon = _num("lon", p["lon"], -180, 180)
                out["lon_min"] = max(-180.0, lon - radius_deg)
                out["lon_max"] = min(180.0, lon + radius_deg)

            if out["lat_min"] >= out["lat_max"] or out["lon_min"] >= out["lon_max"]:
                raise ValueError("Bounding box min must be smaller than max.")

        # depth (dbar ~ metres)
        if "depth" in p:
            d = _num("depth", p["depth"], 0, 6000)
            if self.depth_mode == "slice":
                out["depth_min"] = max(0.0, d - depth_tol)
                out["depth_max"] = d + depth_tol
            else:
                out["depth_min"], out["depth_max"] = 0.0, d
        elif self.fetch_mode == "region":
            out["depth_min"], out["depth_max"] = 0.0, 2000.0

        # dates
        if "date" in p:
            d = _date("date", p["date"])
            out["start_date"] = (d - timedelta(days=date_window_days)).isoformat()
            out["end_date"] = (d + timedelta(days=date_window_days)).isoformat()
        elif "start_date" in p or "end_date" in p:
            if "start_date" not in p or "end_date" not in p:
                raise ValueError("Provide both start_date and end_date, not just one.")
            start = _date("start_date", p["start_date"])
            end = _date("end_date", p["end_date"], end=True)
            if start > end:
                raise ValueError(f"start_date {start} is after end_date {end}.")
            out["start_date"], out["end_date"] = start.isoformat(), end.isoformat()

        # variable
        if "parameter" in p:
            out["parameter"] = _parameter(p["parameter"])
        elif self.default_parameter:
            out["parameter"] = self.default_parameter

        return out


# ============================================================
# Core templates (the 5 in the architecture plan)
# ============================================================

TEMP_BY_REGION = QueryTemplate(
    name="temp_by_region",
    description="Temperature measurements from an ocean region (lat/lon) with optional date/depth.",
    fetch_mode="region",
    required_params=["lat", "lon"],
    optional_params=["date", "start_date", "end_date", "depth"],
    target_chart="map",
    default_parameter="TEMP",
)

SALINITY_BY_FLOAT = QueryTemplate(
    name="salinity_by_float",
    description="Salinity measurements from a specific Argo float (WMO) with optional depth/date.",
    fetch_mode="float",
    required_params=["wmo"],
    optional_params=["depth", "date", "start_date", "end_date"],
    target_chart="line",
    default_parameter="PSAL",
)

PROFILE_BY_DATE = QueryTemplate(
    name="profile_by_date",
    description="Argo profiles near a location around a given date.",
    fetch_mode="region",
    required_params=["lat", "lon", "date"],
    optional_params=["depth"],
    target_chart="line",
)

FLOAT_TRAJECTORY = QueryTemplate(
    name="float_trajectory",
    description="Geographical trajectory of an Argo float over an optional date range.",
    fetch_mode="float",
    required_params=["wmo"],
    optional_params=["start_date", "end_date"],
    target_chart="map",
)

PARAM_BY_DEPTH = QueryTemplate(
    name="param_by_depth",
    description="A parameter (temperature/salinity) at a specific depth in a region.",
    fetch_mode="region",
    required_params=["depth", "lat", "lon"],
    optional_params=["date", "start_date", "end_date", "parameter"],
    target_chart="line",
    depth_mode="slice",
)

# ============================================================
# Additional templates
# ============================================================

PROFILE_BY_FLOAT = QueryTemplate(
    name="profile_by_float",
    description="A specific profile from an Argo float using WMO and cycle number.",
    fetch_mode="profile",
    required_params=["wmo", "cycle"],
    optional_params=["depth", "parameter"],
    target_chart="line",
)

FLOAT_INFO = QueryTemplate(
    name="float_info",
    description="General information and measurements for a specific Argo float.",
    fetch_mode="float",
    required_params=["wmo"],
    optional_params=[],
    target_chart="map",
)

TS_PROFILE = QueryTemplate(
    name="ts_profile",
    description="Temperature + salinity for a profile, for a T-S diagram.",
    fetch_mode="profile",
    required_params=["wmo", "cycle"],
    optional_params=["depth"],
    target_chart="ts_diagram",
)

REGIONAL_TIME_SERIES = QueryTemplate(
    name="regional_time_series",
    description="Ocean measurements from a region over a time period.",
    fetch_mode="region",
    required_params=["lat", "lon", "start_date", "end_date"],
    optional_params=["parameter", "depth"],
    target_chart="time_series",
)

FLOAT_TIME_SERIES = QueryTemplate(
    name="float_time_series",
    description="A parameter from a specific float over time.",
    fetch_mode="float",
    required_params=["wmo", "start_date", "end_date"],
    optional_params=["parameter", "depth"],
    target_chart="time_series",
)

# ============================================================
# Registry + helpers
# ============================================================

TEMPLATES: Dict[str, QueryTemplate] = {
    t.name: t
    for t in [
        TEMP_BY_REGION, SALINITY_BY_FLOAT, PROFILE_BY_DATE, FLOAT_TRAJECTORY,
        PARAM_BY_DEPTH, PROFILE_BY_FLOAT, FLOAT_INFO, TS_PROFILE,
        REGIONAL_TIME_SERIES, FLOAT_TIME_SERIES,
    ]
}


def get_template(name: str) -> QueryTemplate:
    if name not in TEMPLATES:
        raise ValueError(f"Unknown query template: '{name}'. Available: {list(TEMPLATES)}")
    return TEMPLATES[name]


def list_templates() -> List[str]:
    return list(TEMPLATES.keys())


def build_argopy_params(template_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + sanitize + normalize. Called by app.py after intent.py."""
    return get_template(template_name).build_params(params)


def to_argopy_box(built: Dict[str, Any]) -> List[Any]:
    """Region params -> argopy box:
    [lon_min, lon_max, lat_min, lat_max, pres_min, pres_max(, date_min, date_max)]
    Pure data reshaping; fetcher.py passes it to argopy."""
    box: List[Any] = [
        built["lon_min"], built["lon_max"], built["lat_min"], built["lat_max"],
        built["depth_min"], built["depth_max"],
    ]
    if "start_date" in built:
        box += [built["start_date"], built["end_date"]]
    return box


def cache_key(template_name: str, built: Dict[str, Any]) -> str:
    """Deterministic key for cache.py (same query -> same key)."""
    return f"{template_name}:{json.dumps(built, sort_keys=True)}"