"""Pydantic query specification and deterministic hashing for ArgoCard."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Variable(str, Enum):
    """Allowed Argo physical variables for MVP."""

    TEMP = "TEMP"
    PSAL = "PSAL"
    PRES = "PRES"


class DataMode(str, Enum):
    """Argo data delivery modes."""

    RESEARCH = "research"
    STANDARD = "standard"
    EXPERT = "expert"


class Intent(str, Enum):
    """High-level user visualization/analysis intent."""

    PROFILE = "profile"
    MAP = "map"
    TS = "ts"
    TREND = "trend"
    THERMOCLINE = "thermocline"
    TCHP = "tchp"
    ACOUSTIC = "acoustic"


class BoundingBox(BaseModel):
    """Geographic bounding box in degrees [-180, 180] lon, [-90, 90] lat."""

    model_config = ConfigDict(frozen=True)

    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    @model_validator(mode="before")
    @classmethod
    def parse_bbox(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and len(data) == 4:
            return {
                "lon_min": float(data[0]),
                "lon_max": float(data[1]),
                "lat_min": float(data[2]),
                "lat_max": float(data[3]),
            }
        return data


class DateRange(BaseModel):
    """Date interval for observations."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date:
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date()
        if isinstance(v, datetime):
            return v.date()
        return v

    @model_validator(mode="before")
    @classmethod
    def parse_range(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and len(data) == 2:
            return {"start": data[0], "end": data[1]}
        return data


class DepthRange(BaseModel):
    """Pressure / depth range in decibars / meters."""

    model_config = ConfigDict(frozen=True)

    min_depth: float = 0.0
    max_depth: float = 2000.0

    @model_validator(mode="before")
    @classmethod
    def parse_depth(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and len(data) == 2:
            return {"min_depth": float(data[0]), "max_depth": float(data[1])}
        return data


class QuerySpec(BaseModel):
    """Validated, reproducible Argo query specification."""

    model_config = ConfigDict(frozen=True, use_enum_values=False)

    region: BoundingBox
    date_range: DateRange
    variables: list[Variable]
    depth_range: Optional[DepthRange] = None
    mode: DataMode = DataMode.RESEARCH
    intent: Intent

    @model_validator(mode="before")
    @classmethod
    def ensure_physics_variables(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_intent = data.get("intent")
            intent_val = (
                raw_intent.value
                if isinstance(raw_intent, Intent)
                else str(raw_intent).lower()
                if raw_intent is not None
                else ""
            )
            if intent_val in (
                Intent.THERMOCLINE.value,
                Intent.TCHP.value,
                Intent.ACOUSTIC.value,
                "thermocline",
                "tchp",
                "acoustic",
            ):
                vars_list = data.get("variables") or []
                if isinstance(vars_list, (str, Variable)):
                    vars_list = [vars_list]
                else:
                    vars_list = list(vars_list)
                existing_str = {
                    v.value if isinstance(v, Variable) else str(v).upper()
                    for v in vars_list
                }
                for req in [Variable.PRES, Variable.PSAL, Variable.TEMP]:
                    if req.value not in existing_str:
                        vars_list.append(req)
                data["variables"] = vars_list
        return data

    @field_validator("variables", mode="before")
    @classmethod
    def parse_variables(cls, v: Any) -> list[Variable]:
        if isinstance(v, (str, Variable)):
            v = [v]
        parsed: list[Variable] = []
        for item in v:
            if isinstance(item, Variable):
                parsed.append(item)
            elif isinstance(item, str):
                parsed.append(Variable(item.upper()))
            else:
                raise ValueError(f"Invalid variable type: {item}")
        return parsed

    def normalized_dict(self) -> dict[str, Any]:
        """Produce a normalized, canonical dictionary representation."""
        norm_vars = sorted(list({v.value for v in self.variables}))
        return {
            "date_range": {
                "end": self.date_range.end.isoformat(),
                "start": self.date_range.start.isoformat(),
            },
            "depth_range": {
                "max_depth": round(float(self.depth_range.max_depth), 2),
                "min_depth": round(float(self.depth_range.min_depth), 2),
            }
            if self.depth_range is not None
            else None,
            "intent": self.intent.value,
            "mode": self.mode.value,
            "region": {
                "lat_max": round(float(self.region.lat_max), 4),
                "lat_min": round(float(self.region.lat_min), 4),
                "lon_max": round(float(self.region.lon_max), 4),
                "lon_min": round(float(self.region.lon_min), 4),
            },
            "variables": norm_vars,
        }

    def normalized_json(self) -> str:
        """Produce a deterministic, whitespace-stripped, sorted JSON string."""
        return json.dumps(self.normalized_dict(), sort_keys=True, separators=(",", ":"))

    def spec_hash(self) -> str:
        """Calculate the SHA-256 hash of the normalized JSON representation."""
        return hashlib.sha256(self.normalized_json().encode("utf-8")).hexdigest()

    def fetch_dict(self) -> dict[str, Any]:
        """Produce a normalized canonical dictionary excluding intent for data caching."""
        d = self.normalized_dict()
        d.pop("intent", None)
        return d

    def fetch_json(self) -> str:
        """Produce deterministic JSON of fetch parameters (excluding intent)."""
        return json.dumps(self.fetch_dict(), sort_keys=True, separators=(",", ":"))

    def fetch_key(self) -> str:
        """Calculate the SHA-256 hash of fetch parameters (region, date_range, depth_range, variables, mode)."""
        return hashlib.sha256(self.fetch_json().encode("utf-8")).hexdigest()

