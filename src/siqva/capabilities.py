"""Capability profiles declaring data needs, display modes, and default depths per visualization intent.

One source of truth shared by validation, planning, the Query Terminal, and the Plot Graph page.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict

from .spec import DepthRange, Intent, QuerySpec


class DataNeed(str, Enum):
    """Data requirement for visualization and analysis modules."""

    METADATA = "metadata"            # Needs only float index (positions, counts); no profiles
    SAMPLE_OK = "sample_ok"          # Can render individual profiles from a deterministic sample
    FULL_REQUIRED = "full_required"  # Requires complete regional dataset (climatology, hovmoller, drift)


class CapabilityProfile(BaseModel):
    """Capability profile for an Intent module."""

    model_config = ConfigDict(frozen=True)

    intent: Intent
    data_need: DataNeed
    default_depth: Optional[DepthRange]
    per_profile_only: bool
    label: str
    description: str = ""


# Table-driven capability profile mapping (one source of truth)
CAPABILITY_PROFILES: dict[Intent, CapabilityProfile] = {
    Intent.PROFILE: CapabilityProfile(
        intent=Intent.PROFILE,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=False,
        label="Temperature vs Depth Profile",
        description="Vertical profiles of temperature or salinity against depth/pressure.",
    ),
    Intent.MAP: CapabilityProfile(
        intent=Intent.MAP,
        data_need=DataNeed.METADATA,
        default_depth=None,
        per_profile_only=False,
        label="Float Position Map",
        description="Geographic overview of active Argo floats and surface positions.",
    ),
    Intent.TS: CapabilityProfile(
        intent=Intent.TS,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=False,
        label="Temperature vs Salinity (T-S)",
        description="Water property diagram comparing temperature and practical salinity.",
    ),
    Intent.TREND: CapabilityProfile(
        intent=Intent.TREND,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=False,
        label="Time-Series Trend",
        description="Chronological time series of oceanographic observations.",
    ),
    Intent.THERMOCLINE: CapabilityProfile(
        intent=Intent.THERMOCLINE,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=True,
        label="Thermocline & Barrier Layer",
        description="Mixed layer depth (MLD), isothermal layer depth (ILD), barrier layer, and 20°C isotherm.",
    ),
    Intent.TCHP: CapabilityProfile(
        intent=Intent.TCHP,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=True,
        label="Cyclone Heat Potential (TCHP)",
        description="Upper ocean heat content integrated relative to the 26°C isotherm.",
    ),
    Intent.ACOUSTIC: CapabilityProfile(
        intent=Intent.ACOUSTIC,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=2000.0),
        per_profile_only=True,
        label="Acoustic Sound Speed",
        description="TEOS-10 sound speed profile, sonic layer depth, and SOFAR channel axis.",
    ),
    Intent.BUOYANCY: CapabilityProfile(
        intent=Intent.BUOYANCY,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=True,
        label="Buoyancy & Stability",
        description="Brunt-Väisälä buoyancy frequency squared (N²) stratification profile.",
    ),
    Intent.TS_ISOPYCNAL: CapabilityProfile(
        intent=Intent.TS_ISOPYCNAL,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=False,
        label="T-S with Isopycnals",
        description="Temperature-salinity diagram overlaid with potential density contours.",
    ),
    Intent.OMZ: CapabilityProfile(
        intent=Intent.OMZ,
        data_need=DataNeed.SAMPLE_OK,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=True,
        label="Oxygen Minimum Zone",
        description="Dissolved oxygen vertical profile and hypoxic / suboxic ceiling detection.",
    ),
    Intent.HOVMOLLER: CapabilityProfile(
        intent=Intent.HOVMOLLER,
        data_need=DataNeed.FULL_REQUIRED,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=False,
        label="Hovmoller Diagram",
        description="Hovmøller space-time contour diagram requiring complete observations.",
    ),
    Intent.CLIMATOLOGY: CapabilityProfile(
        intent=Intent.CLIMATOLOGY,
        data_need=DataNeed.FULL_REQUIRED,
        default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
        per_profile_only=False,
        label="Climatology Envelope",
        description="Regional mean envelope with standard deviation bands requiring full data.",
    ),
    Intent.DRIFT: CapabilityProfile(
        intent=Intent.DRIFT,
        data_need=DataNeed.FULL_REQUIRED,
        default_depth=DepthRange(min_depth=0.0, max_depth=20.0),
        per_profile_only=False,
        label="Float Drift Velocity",
        description="Lagrangian surface drift speed tracking requiring all float cycles.",
    ),
}


def get_capability_profile(intent: Intent) -> CapabilityProfile:
    """Return the CapabilityProfile for the given Intent."""
    if intent not in CAPABILITY_PROFILES:
        # Fallback profile
        return CapabilityProfile(
            intent=intent,
            data_need=DataNeed.SAMPLE_OK,
            default_depth=DepthRange(min_depth=0.0, max_depth=500.0),
            per_profile_only=False,
            label=intent.value.title(),
        )
    return CAPABILITY_PROFILES[intent]


def resolve_effective_depth(spec: QuerySpec) -> tuple[Optional[DepthRange], bool]:
    """Resolve effective depth range for a spec.

    Returns:
        (depth_range, is_default): Tuple of DepthRange (or None for METADATA) and
        a boolean indicating whether the depth is a system default (True) or user-specified (False).
    """
    if spec.depth_range is not None:
        # User specified depth always wins
        return spec.depth_range, False

    prof = get_capability_profile(spec.intent)
    return prof.default_depth, True

