"""Deterministic TEOS-10 Ocean Physics Engine for ArgoCard.

Computes Mixed Layer Depth (MLD), Isothermal Layer Depth (ILD), Barrier Layer Thickness (BLT),
Z20 Thermocline Proxy, Tropical Cyclone Heat Potential (TCHP, Z26), and TEOS-10 Acoustic Properties
(Sound Speed, Sonic Layer Depth, SOFAR Channel Axis).

Strictly deterministic, zero LLM reliance.
"""

from __future__ import annotations

from typing import Any, Optional
import gsw
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))


class ProfilePhysicsSummary(BaseModel):
    """Deterministic TEOS-10 ocean physics summary for a single Argo profile."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    wmo_id: str
    cycle: int
    date: str
    lat: float
    lon: float
    max_depth_m: float
    sst_c: float
    sss_psu: float
    mld_dens_m: Optional[float] = None
    ild_temp_m: Optional[float] = None
    barrier_layer_m: Optional[float] = None
    z20_isotherm_m: Optional[float] = None
    z26_isotherm_m: Optional[float] = None
    tchp_kj_cm2: float = 0.0
    sld_m: Optional[float] = None
    sofar_axis_m: Optional[float] = None
    water_mass_heuristic: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


class DatasetPhysicsSummary(BaseModel):
    """Aggregate statistics across multiple analyzed profiles."""

    model_config = ConfigDict(frozen=True)

    total_profiles: int
    mean_mld_dens_m: Optional[float] = None
    min_mld_dens_m: Optional[float] = None
    max_mld_dens_m: Optional[float] = None
    mean_ild_temp_m: Optional[float] = None
    mean_barrier_layer_m: Optional[float] = None
    mean_z20_isotherm_m: Optional[float] = None
    mean_tchp_kj_cm2: Optional[float] = None
    max_tchp_kj_cm2: Optional[float] = None
    mean_sld_m: Optional[float] = None
    mean_sofar_axis_m: Optional[float] = None


THERMOCLINE_DISCLAIMER = (
    "Scientific Guardrail / Disclaimer: Mixed Layer Depth (MLD), Isothermal Layer Depth (ILD), "
    "and the 20°C isotherm (Z20) serve as physical proxies for thermocline structure and pelagic habitat depth. "
    "They are physical oceanographic indicators, NOT standalone commercial fish-catch predictions. "
    "Commercial fisheries distribution and pelagic fish behavior additionally depend on dissolved oxygen, "
    "chlorophyll-a / primary productivity, prey availability, and local ecological regulations."
)

CYCLONE_TCHP_DISCLAIMER = (
    "Scientific Guardrail / Disclaimer: Citing Leipper & Volgenau (1972) and Mainelli et al. (2008), "
    "Tropical Cyclone Heat Potential (TCHP) values exceeding ~60–80 kJ/cm² indicate a significant upper-ocean "
    "thermal reservoir favorable for rapid tropical cyclone intensification. However, TCHP is strictly an "
    "ocean thermodynamic metric; whether a cyclone actually forms or intensifies is governed by atmospheric "
    "conditions, particularly low vertical wind shear, mid-tropospheric humidity, and atmospheric instability."
)

ACOUSTIC_DISCLAIMER = (
    "Scientific Guardrail / Disclaimer: TEOS-10 sound speed is derived from Absolute Salinity, Conservative "
    "Temperature, and pressure via gsw.sound_speed. The Sonic Layer Depth (SLD) marks the near-surface acoustic "
    "duct maximum. The SOFAR (Sound Fixing and Ranging) channel axis is the deep sound speed minimum and is "
    "strictly set to None whenever a profile's max_depth_m < 1000 metres, as shallow profiles do not sample "
    "the deep acoustic waveguide."
)


def _first_downward_crossing(depth_m: np.ndarray, vals: np.ndarray, target: float) -> Optional[float]:
    """Find the first downward crossing of a target value with linear interpolation."""
    for i in range(len(vals) - 1):
        v0, v1 = vals[i], vals[i + 1]
        if v0 >= target and v1 < target:
            frac = 0.0 if v0 == v1 else (target - v0) / (v1 - v0)
            return float(depth_m[i] + frac * (depth_m[i + 1] - depth_m[i]))
    return None


def _first_upward_crossing(depth_m: np.ndarray, vals: np.ndarray, target: float) -> Optional[float]:
    """Find the first upward crossing of a target value with linear interpolation."""
    for i in range(len(vals) - 1):
        v0, v1 = vals[i], vals[i + 1]
        if v0 <= target and v1 > target:
            frac = 0.0 if v1 == v0 else (target - v0) / (v1 - v0)
            return float(depth_m[i] + frac * (depth_m[i + 1] - depth_m[i]))
    return None


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame columns to support both argopy standard names and lowercase aliases."""
    col_map = {
        "PLATFORM_NUMBER": "wmo_id",
        "CYCLE_NUMBER": "cycle",
        "TIME": "time",
        "LATITUDE": "lat",
        "LONGITUDE": "lon",
        "PRES": "pres",
        "TEMP": "temp",
        "PSAL": "psal",
    }
    df = df.copy()
    for standard, alias in col_map.items():
        if standard in df.columns and alias not in df.columns:
            df[alias] = df[standard]
        elif alias in df.columns and standard not in df.columns:
            df[standard] = df[alias]
    return df


def compute_new_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[ProfilePhysicsSummary]]:
    """Compute deterministic TEOS-10 derived ocean physics features for Argo profiles.

    Expects DataFrame with columns:
    ['wmo_id' or 'PLATFORM_NUMBER', 'cycle' or 'CYCLE_NUMBER', 'time' or 'TIME',
     'lat' or 'LATITUDE', 'lon' or 'LONGITUDE', 'pres' or 'PRES',
     'temp' or 'TEMP', 'psal' or 'PSAL']

    Returns:
        (enriched_df, list_of_ProfilePhysicsSummary)
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame(), []

    df = _normalize_column_names(df)

    required = ["pres", "temp", "psal", "lat", "lon"]
    for col in required:
        if col not in df.columns:
            return df, []

    p = pd.to_numeric(df["pres"], errors="coerce").to_numpy(dtype=float)
    t = pd.to_numeric(df["temp"], errors="coerce").to_numpy(dtype=float)
    sp = pd.to_numeric(df["psal"], errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)

    # Valid mask for thermodynamic calculations
    valid = np.isfinite(p) & np.isfinite(t) & np.isfinite(sp) & np.isfinite(lat) & np.isfinite(lon)
    if not np.any(valid):
        return df, []

    # Convert pressure to geometric depth and compute TEOS-10 derived quantities
    depth_m = np.full_like(p, np.nan)
    sa = np.full_like(p, np.nan)
    ct = np.full_like(p, np.nan)
    sig0 = np.full_like(p, np.nan)
    rho = np.full_like(p, np.nan)
    snd = np.full_like(p, np.nan)

    depth_m[valid] = -gsw.z_from_p(p[valid], lat[valid])
    sa[valid] = gsw.SA_from_SP(sp[valid], p[valid], lon[valid], lat[valid])
    ct[valid] = gsw.CT_from_t(sa[valid], t[valid], p[valid])
    sig0[valid] = gsw.sigma0(sa[valid], ct[valid])
    rho[valid] = gsw.rho(sa[valid], ct[valid], p[valid])
    snd[valid] = gsw.sound_speed(sa[valid], ct[valid], p[valid])

    df["depth_m"] = depth_m
    df["sa"] = sa
    df["ct"] = ct
    df["sigma0"] = sig0
    df["rho"] = rho
    df["sound_speed"] = snd

    summaries: list[ProfilePhysicsSummary] = []
    cp0 = 3991.86795711963  # TEOS-10 standard specific heat capacity of seawater (J/(kg*K))

    group_cols = ["wmo_id", "cycle"] if ("wmo_id" in df.columns and "cycle" in df.columns) else []
    if not group_cols:
        return df, summaries

    for (wmo, cycle), grp in df.groupby(group_cols):
        grp = grp.dropna(subset=["depth_m", "temp", "psal", "sigma0", "rho", "sound_speed"])
        grp = grp.sort_values("depth_m").drop_duplicates(subset=["depth_m"])
        if len(grp) < 5:
            continue

        z_m = grp["depth_m"].to_numpy(dtype=float)
        temp = grp["temp"].to_numpy(dtype=float)
        psal = grp["psal"].to_numpy(dtype=float)
        sig0_p = grp["sigma0"].to_numpy(dtype=float)
        dens = grp["rho"].to_numpy(dtype=float)
        snd_p = grp["sound_speed"].to_numpy(dtype=float)

        if z_m[0] > 15.0:
            continue

        lat0 = float(grp["lat"].iloc[0])
        lon0 = float(grp["lon"].iloc[0])
        max_depth = float(z_m[-1])

        # 1. 10m Reference MLD, ILD & Barrier Layer (de Boyer Montégut et al., 2004)
        ref_z = 10.0 if z_m[0] <= 10.0 <= max_depth else float(z_m[0])
        t_ref = float(np.interp(ref_z, z_m, temp))
        sig_ref = float(np.interp(ref_z, z_m, sig0_p))

        sub = z_m >= ref_z
        mld_dens = _first_upward_crossing(z_m[sub], sig0_p[sub], sig_ref + 0.03)
        ild_temp = _first_downward_crossing(z_m[sub], temp[sub], t_ref - 0.2)
        blt = (
            round(max(0.0, ild_temp - mld_dens), 1)
            if (mld_dens is not None and ild_temp is not None)
            else None
        )

        # 2. 20°C Isotherm (First downward crossing)
        z20 = _first_downward_crossing(z_m, temp, 20.0) if temp[0] >= 20.0 else None

        # 3. Contiguous Upper-Layer TCHP above 26°C (Leipper & Volgenau, 1972)
        tchp = 0.0
        z26 = _first_downward_crossing(z_m, temp, 26.0) if temp[0] > 26.0 else None
        if z26 is not None:
            idx = np.where(z_m < z26)[0]
            z_int = np.append(z_m[idx], z26)
            t_int = np.append(temp[idx], 26.0)
            rho_int = np.append(dens[idx], float(np.interp(z26, z_m, dens)))
            heat_j_m2 = float(_trapz(rho_int * cp0 * (t_int - 26.0), z_int))
            tchp = round(max(0.0, heat_j_m2 / 1e7), 1)

        # 4. Sonic Layer Depth & Depth-Checked SOFAR Axis
        sld_cap = min(300.0, z20 if z20 is not None else 300.0)
        up_mask = z_m <= max(sld_cap, 30.0)
        sld = float(z_m[up_mask][np.argmax(snd_p[up_mask])]) if np.any(up_mask) else None
        sofar = float(z_m[np.argmin(snd_p)]) if max_depth >= 1000.0 else None

        # 5. Subsurface Isopycnal Water-Mass Heuristic
        iso_mask = (sig0_p >= 23.5) & (sig0_p <= 25.5)
        max_sub_sal = float(np.max(psal[iso_mask])) if np.any(iso_mask) else float(psal[0])
        if lat0 < -5.0:
            wm = "Southern Indian Ocean Water (Heuristic)"
        elif max_sub_sal >= 35.8 and lat0 >= 5.0:
            wm = "Arabian Sea High Salinity Water (ASHSW Heuristic, sigma0 23.5-25.5)"
        elif float(psal[0]) <= 33.5 and lat0 >= 5.0:
            wm = "Bay of Bengal Low-Salinity Plume (BoBW Heuristic)"
        else:
            wm = "Equatorial / Transitional Indian Ocean Water (Heuristic)"

        time_val = grp["time"].iloc[0] if "time" in grp.columns else "N/A"
        date_str = str(time_val)[:10]

        summaries.append(
            ProfilePhysicsSummary(
                profile_id=f"{wmo}_{cycle}",
                wmo_id=str(wmo),
                cycle=int(cycle),
                date=date_str,
                lat=round(lat0, 4),
                lon=round(lon0, 4),
                max_depth_m=round(max_depth, 1),
                sst_c=round(float(temp[0]), 2),
                sss_psu=round(float(psal[0]), 2),
                mld_dens_m=round(mld_dens, 1) if mld_dens is not None else None,
                ild_temp_m=round(ild_temp, 1) if ild_temp is not None else None,
                barrier_layer_m=blt,
                z20_isotherm_m=round(z20, 1) if z20 is not None else None,
                z26_isotherm_m=round(z26, 1) if z26 is not None else None,
                tchp_kj_cm2=tchp,
                sld_m=round(sld, 1) if sld is not None else None,
                sofar_axis_m=round(sofar, 1) if sofar is not None else None,
                water_mass_heuristic=wm,
            )
        )

    return df, summaries


def build_feature_context(intent: str, summaries: list[Any]) -> str:
    """Format computed metrics for contextual reporting and append mandatory scientific disclaimers."""
    if not summaries:
        return "No profile data available for the requested feature context."

    lines: list[str] = []
    normalized_intent = intent.strip().lower()

    lines.append(f"### OCEANOGRAPHIC FEATURE ANALYSIS CONTEXT (Intent: {intent})")
    lines.append(f"Total Profiles Analyzed: {len(summaries)}\n")

    for i, s in enumerate(summaries, 1):
        prof_id = s.get("profile_id", f"Profile #{i}")
        wmo = s.get("wmo_id", "N/A")
        cycle = s.get("cycle", "N/A")
        date_str = s.get("date", "N/A")
        lat = s.get("lat", "N/A")
        lon = s.get("lon", "N/A")
        max_z = s.get("max_depth_m", "N/A")
        sst = s.get("sst_c", "N/A")
        sss = s.get("sss_psu", "N/A")
        wm = s.get("water_mass_heuristic", "Unclassified")

        lines.append(f"#### Profile {prof_id} (WMO: {wmo}, Cycle: {cycle})")
        lines.append(f"- Location: Lat {lat}°, Lon {lon}° | Date: {date_str}")
        lines.append(f"- Sampling Depth: {max_z} m | SST: {sst} °C | SSS: {sss} PSU")
        lines.append(f"- Water Mass: {wm}")

        if normalized_intent in ("thermocline_mld", "thermocline", "all"):
            mld = s.get("mld_dens_m")
            ild = s.get("ild_temp_m")
            blt = s.get("barrier_layer_m")
            z20 = s.get("z20_isotherm_m")
            lines.append("  [Thermocline & Barrier Layer Metrics]")
            lines.append(
                f"  • Density MLD (Δσ0 = +0.03 kg/m³ from 10m): {mld} m"
                if mld is not None
                else "  • Density MLD: Not reached"
            )
            lines.append(
                f"  • Isothermal Layer Depth (ΔT = -0.2°C from 10m): {ild} m"
                if ild is not None
                else "  • Temp ILD: Not reached"
            )
            lines.append(
                f"  • Barrier Layer Thickness (BLT = max(0, ILD - MLD)): {blt} m"
                if blt is not None
                else "  • Barrier Layer Thickness: N/A"
            )
            lines.append(
                f"  • 20°C Isotherm Depth (Z20 Thermocline Proxy): {z20} m"
                if z20 is not None
                else "  • Z20 Isotherm: Not reached"
            )

        if normalized_intent in ("cyclone_tchp", "tchp", "all"):
            tchp = s.get("tchp_kj_cm2", 0.0)
            z26 = s.get("z26_isotherm_m")
            lines.append("  [Tropical Cyclone Heat Potential Metrics]")
            lines.append(
                f"  • 26°C Isotherm Depth (Z26): {z26} m"
                if z26 is not None
                else "  • 26°C Isotherm (Z26): Surface < 26°C"
            )
            lines.append(f"  • TCHP (0 to Z26 integral): {tchp} kJ/cm²")

        if normalized_intent in ("acoustic_profile", "acoustic", "all"):
            sld = s.get("sld_m")
            sofar = s.get("sofar_axis_m")
            lines.append("  [TEOS-10 Acoustic Properties]")
            lines.append(
                f"  • Sonic Layer Depth (SLD Peak): {sld} m"
                if sld is not None
                else "  • Sonic Layer Depth: N/A"
            )
            if sofar is not None:
                lines.append(f"  • SOFAR Channel Axis (Sound Speed Minimum): {sofar} m")
            else:
                lines.append(
                    f"  • SOFAR Channel Axis: None (max_depth_m = {max_z} m < 1000.0 m threshold)"
                )

        lines.append("")

    lines.append("---")
    lines.append("### MANDATORY SCIENTIFIC GUARDRAILS & CITATIONS")

    if normalized_intent in ("thermocline_mld", "thermocline", "all"):
        lines.append(f"- **Thermocline & MLD**: {THERMOCLINE_DISCLAIMER}")
    if normalized_intent in ("cyclone_tchp", "tchp", "all"):
        lines.append(f"- **Cyclone TCHP**: {CYCLONE_TCHP_DISCLAIMER}")
    if normalized_intent in ("acoustic_profile", "acoustic", "all"):
        lines.append(f"- **Acoustic Profiling**: {ACOUSTIC_DISCLAIMER}")

    if normalized_intent not in (
        "thermocline_mld",
        "thermocline",
        "cyclone_tchp",
        "tchp",
        "acoustic_profile",
        "acoustic",
        "all",
    ):
        lines.append(f"- **Thermocline & MLD**: {THERMOCLINE_DISCLAIMER}")
        lines.append(f"- **Cyclone TCHP**: {CYCLONE_TCHP_DISCLAIMER}")
        lines.append(f"- **Acoustic Profiling**: {ACOUSTIC_DISCLAIMER}")

    return "\n".join(lines)
