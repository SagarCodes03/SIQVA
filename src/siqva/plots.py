"""Plotly visualization templates for SIQVA following the Deep Ocean dark theme."""

from __future__ import annotations

import os
import time
from typing import Any, Optional
try:
    import gsw
except ImportError:
    gsw = None
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .spec import Variable

# Deep Ocean Dark Theme Palette
THEME_BG = "rgba(0, 0, 0, 0)"
THEME_GRID = "#1E4558"
THEME_TEXT = "#E6F1F5"
COLOR_PRIMARY_TEAL = "#2EC4B6"
COLOR_AMBER = "#FFB703"
COLOR_TEMP = "#FF8C42"  # warm orange
COLOR_PSAL = "#2EC4B6"  # teal
COLOR_PRES = "#8FA9B8"  # muted blue-grey

# Maximum per-row observations rendered in scatter plots to keep JSON payloads lightweight
MAX_PLOT_OBSERVATIONS: int = 5000


def _stratified_sample_observations(
    df: pd.DataFrame,
    max_points: int = MAX_PLOT_OBSERVATIONS,
) -> pd.DataFrame:
    """Deterministically downsample observations stratified by profile to at most max_points."""
    if len(df) <= max_points:
        return df

    # Find profile grouping column(s)
    group_cols: list[str] = []
    if "PLATFORM_NUMBER" in df.columns and "CYCLE_NUMBER" in df.columns:
        group_cols = ["PLATFORM_NUMBER", "CYCLE_NUMBER"]
    elif "PLATFORM_NUMBER" in df.columns:
        group_cols = ["PLATFORM_NUMBER"]
    elif "wmo_id" in df.columns and "cycle" in df.columns:
        group_cols = ["wmo_id", "cycle"]
    elif "wmo_id" in df.columns:
        group_cols = ["wmo_id"]

    if not group_cols:
        # No profile metadata; use deterministic uniform index sampling
        indices = np.linspace(0, len(df) - 1, max_points, dtype=int)
        return df.iloc[np.unique(indices)].copy()

    # Stratified by profile: allocate sample quota per profile
    groups = [group for _, group in df.groupby(group_cols, sort=True)]
    n_groups = len(groups)
    if n_groups == 0:
        return df

    total_rows = len(df)
    target_ratio = max_points / total_rows

    selected_indices: list[int] = []
    for g in groups:
        g_len = len(g)
        k = max(1, int(round(g_len * target_ratio)))
        # Select evenly spaced indices within group to preserve surface and deep structure
        local_idx = np.unique(np.round(np.linspace(0, g_len - 1, k)).astype(int))
        selected_indices.extend(g.index[local_idx].tolist())

    selected_indices = sorted(set(selected_indices))
    if len(selected_indices) > max_points:
        sub_idx = np.round(np.linspace(0, len(selected_indices) - 1, max_points)).astype(int)
        selected_indices = [selected_indices[i] for i in sub_idx]

    return df.loc[selected_indices].copy()


def apply_theme(fig: go.Figure, title: Optional[str] = None) -> go.Figure:
    """Apply the shared Deep Ocean Plotly theme to a figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=THEME_BG,
        plot_bgcolor=THEME_BG,
        font=dict(color=THEME_TEXT, family="sans serif"),
        margin=dict(l=50, r=30, t=50, b=50),
    )
    if title:
        fig.update_layout(title=dict(text=title, font=dict(color=THEME_TEXT, size=16)))

    fig.update_xaxes(
        gridcolor=THEME_GRID,
        zerolinecolor=THEME_GRID,
        tickfont=dict(color=THEME_TEXT),
        title_font=dict(color=THEME_TEXT),
    )
    fig.update_yaxes(
        gridcolor=THEME_GRID,
        zerolinecolor=THEME_GRID,
        tickfont=dict(color=THEME_TEXT),
        title_font=dict(color=THEME_TEXT),
    )
    return fig


def _variable_unit(var_name: str) -> str:
    """Return standard oceanographic units for a variable."""
    if "TEMP" in var_name:
        return "°C"
    elif "PSAL" in var_name:
        return "PSS-78"
    elif "PRES" in var_name:
        return "dbar"
    return ""


def plot_depth_profile(
    df: Optional[pd.DataFrame],
    variable: Variable | str = Variable.TEMP,
    max_profiles: int = 25,
    title: Optional[str] = None,
) -> go.Figure:
    """Draw vertical depth profiles (variable vs inverted pressure axis).

    One trace per profile (PLATFORM_NUMBER + CYCLE_NUMBER), capped at max_profiles
    with a visible note when capped. Handles empty and single-profile datasets.
    """
    var_str = variable.value if isinstance(variable, Variable) else str(variable)
    fig = go.Figure()

    if df is None or len(df) == 0:
        fig.add_annotation(
            text="No profile data available for this query.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        fig.update_layout(
            xaxis_title=f"{var_str} ({_variable_unit(var_str)})",
            yaxis_title="Pressure (dbar)",
            yaxis=dict(autorange="reversed"),
        )
        return apply_theme(fig, title=title or f"Depth Profile: {var_str}")

    pres_col = "PRES" if "PRES" in df.columns else None
    if not pres_col or var_str not in df.columns:
        fig.add_annotation(
            text=f"Required columns (PRES, {var_str}) not present in dataset.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=COLOR_AMBER, size=14),
        )
        return apply_theme(fig, title=title or f"Depth Profile: {var_str}")

    has_plat = "PLATFORM_NUMBER" in df.columns
    has_cyc = "CYCLE_NUMBER" in df.columns

    if has_plat and has_cyc:
        profiles = list(df.groupby(["PLATFORM_NUMBER", "CYCLE_NUMBER"]))
    elif has_cyc:
        profiles = list(df.groupby("CYCLE_NUMBER"))
    else:
        profiles = [(("Single", "1"), df)]

    total_profiles = len(profiles)
    capped = total_profiles > max_profiles
    profiles_to_plot = profiles[:max_profiles]

    base_color = COLOR_TEMP if "TEMP" in var_str else (COLOR_PSAL if "PSAL" in var_str else COLOR_PRES)

    for idx, (p_id, group) in enumerate(profiles_to_plot):
        clean_grp = group.dropna(subset=[var_str, pres_col]).sort_values(by=pres_col)
        if clean_grp.empty:
            continue

        label = f"WMO {p_id[0]} Cyc {p_id[1]}" if isinstance(p_id, tuple) else f"Profile {p_id}"
        # Slight opacity for multiple traces
        opacity = 0.85 if total_profiles == 1 else 0.65

        fig.add_trace(
            go.Scatter(
                x=clean_grp[var_str],
                y=clean_grp[pres_col],
                mode="lines",
                name=label,
                line=dict(width=1.5, color=base_color),
                opacity=opacity,
                hovertemplate=f"<b>{label}</b><br>{var_str}: %{{x:.2f}}<br>PRES: %{{y:.1f}} dbar<extra></extra>",
            )
        )

    if capped:
        fig.add_annotation(
            text=f"Showing {max_profiles} of {total_profiles} profiles (capped)",
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.98,
            xanchor="left",
            yanchor="top",
            showarrow=False,
            bgcolor="#12303F",
            bordercolor=COLOR_AMBER,
            borderwidth=1,
            font=dict(color=COLOR_AMBER, size=12),
        )

    unit_str = _variable_unit(var_str)
    axis_label = f"{var_str} ({unit_str})" if unit_str else var_str

    fig.update_layout(
        xaxis_title=axis_label,
        yaxis_title="Pressure (dbar)",
        yaxis=dict(autorange="reversed"),
        showlegend=(total_profiles <= 10),
    )

    default_title = f"Depth Profile: {var_str}" + (f" ({total_profiles} profiles)" if total_profiles > 1 else "")
    return apply_theme(fig, title=title or default_title)


def plot_ts_diagram(
    df: Optional[pd.DataFrame],
    title: Optional[str] = None,
) -> go.Figure:
    """Draw Temperature-Salinity (T-S) diagram colored by pressure."""
    fig = go.Figure()

    if df is None or len(df) == 0:
        fig.add_annotation(
            text="No observation data available for T-S diagram.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        fig.update_layout(
            xaxis_title="Practical Salinity (PSAL)",
            yaxis_title="Temperature (°C)",
        )
        return apply_theme(fig, title=title or "Temperature-Salinity (T-S) Diagram")

    if "TEMP" not in df.columns or "PSAL" not in df.columns:
        fig.add_annotation(
            text="T-S diagram requires both TEMP and PSAL variables in the dataset.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=COLOR_AMBER, size=14),
        )
        fig.update_layout(
            xaxis_title="Practical Salinity (PSAL)",
            yaxis_title="Temperature (°C)",
        )
        return apply_theme(fig, title=title or "Temperature-Salinity (T-S) Diagram")

    cols_to_drop = ["TEMP", "PSAL"]
    pres_col = "PRES" if "PRES" in df.columns else None
    if pres_col:
        cols_to_drop.append(pres_col)

    valid_df = df.dropna(subset=cols_to_drop)
    if valid_df.empty:
        fig.add_annotation(
            text="No valid (non-null) TEMP and PSAL pairs found.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Temperature-Salinity (T-S) Diagram")

    total_obs = len(valid_df)
    sampled_df = _stratified_sample_observations(valid_df, max_points=MAX_PLOT_OBSERVATIONS)
    is_sampled = len(sampled_df) < total_obs

    ScatterTrace = getattr(go, "Scattergl", go.Scatter)

    if pres_col:
        marker_dict = dict(
            size=4,
            color=sampled_df[pres_col],
            colorscale="Viridis",
            colorbar=dict(
                title=dict(text="Pressure (dbar)", font=dict(color=THEME_TEXT)),
                tickfont=dict(color=THEME_TEXT),
            ),
            opacity=0.75,
        )
    else:
        marker_dict = dict(size=4, color=COLOR_PRIMARY_TEAL, opacity=0.75)

    fig.add_trace(
        ScatterTrace(
            x=sampled_df["PSAL"],
            y=sampled_df["TEMP"],
            mode="markers",
            marker=marker_dict,
            hovertemplate="Salinity: %{x:.2f}<br>Temp: %{y:.2f} °C<extra></extra>",
        )
    )

    if is_sampled:
        fig.add_annotation(
            text=f"Showing {len(sampled_df):,} of {total_obs:,} observations (sampled)",
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.98,
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font=dict(color=THEME_TEXT, size=11),
            bgcolor="rgba(10, 25, 40, 0.7)",
            bordercolor=THEME_GRID,
            borderwidth=1,
        )

    fig.update_layout(
        xaxis_title="Practical Salinity (PSAL)",
        yaxis_title="Temperature (°C)",
    )
    return apply_theme(fig, title=title or "Temperature-Salinity (T-S) Diagram")


def plot_position_map(
    df: Optional[pd.DataFrame],
    selected_profile: Optional[tuple[Any, Any]] = None,
    title: Optional[str] = None,
) -> go.Figure:
    """Draw geographic scatter position map of float trajectories and profile locations."""
    fig = go.Figure()

    if df is None or len(df) == 0:
        fig.add_annotation(
            text="No position data available to plot.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Float Locations and Tracks")

    lat_col = "LATITUDE" if "LATITUDE" in df.columns else ("latitude" if "latitude" in df.columns else None)
    lon_col = "LONGITUDE" if "LONGITUDE" in df.columns else ("longitude" if "longitude" in df.columns else None)

    if not lat_col or not lon_col:
        fig.add_annotation(
            text="Coordinate columns (LATITUDE, LONGITUDE) not present.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=COLOR_AMBER, size=14),
        )
        return apply_theme(fig, title=title or "Float Locations and Tracks")

    clean_coords = df.dropna(subset=[lat_col, lon_col])
    if clean_coords.empty:
        fig.add_annotation(
            text="No valid coordinates found.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Float Locations and Tracks")

    has_plat = "PLATFORM_NUMBER" in clean_coords.columns
    has_cyc = "CYCLE_NUMBER" in clean_coords.columns

    if has_plat:
        floats = list(clean_coords.groupby("PLATFORM_NUMBER"))
    else:
        floats = [("Float", clean_coords)]

    for wmo, float_data in floats:
        # Group by cycle or time to get ordered locations
        order_col = "TIME" if "TIME" in float_data.columns else ("CYCLE_NUMBER" if "CYCLE_NUMBER" in float_data.columns else None)
        ordered = float_data.sort_values(by=order_col) if order_col else float_data
        # Drop duplicates so we have one marker per profile location
        if has_cyc:
            locs = ordered.drop_duplicates(subset=["CYCLE_NUMBER"])
        else:
            locs = ordered.drop_duplicates(subset=[lat_col, lon_col])

        fig.add_trace(
            go.Scattergeo(
                lon=locs[lon_col],
                lat=locs[lat_col],
                mode="lines+markers",
                name=f"WMO {wmo}",
                line=dict(width=1.5, color=COLOR_PRIMARY_TEAL),
                marker=dict(size=6, color=COLOR_PRIMARY_TEAL),
                hovertemplate=f"WMO: {wmo}<br>Lat: %{{lat:.2f}}<br>Lon: %{{lon:.2f}}<extra></extra>",
            )
        )

    # Highlight selected profile in amber if provided
    if selected_profile and has_plat and has_cyc:
        sel_wmo, sel_cyc = selected_profile
        sel_row = clean_coords[(clean_coords["PLATFORM_NUMBER"] == sel_wmo) & (clean_coords["CYCLE_NUMBER"] == sel_cyc)]
        if not sel_row.empty:
            pt = sel_row.iloc[0]
            fig.add_trace(
                go.Scattergeo(
                    lon=[pt[lon_col]],
                    lat=[pt[lat_col]],
                    mode="markers",
                    name=f"Selected (WMO {sel_wmo} Cyc {sel_cyc})",
                    marker=dict(size=12, color=COLOR_AMBER, symbol="star"),
                    hovertemplate=f"Selected: WMO {sel_wmo} Cyc {sel_cyc}<br>Lat: %{{lat:.2f}}<br>Lon: %{{lon:.2f}}<extra></extra>",
                )
            )

    fig.update_geos(
        projection_type="natural earth",
        showland=True,
        landcolor="#12303F",
        showocean=True,
        oceancolor="#0B1F2A",
        showcountries=True,
        countrycolor="#1E4558",
        coastlinecolor="#1E4558",
        bgcolor=THEME_BG,
    )

    return apply_theme(fig, title=title or "Float Locations and Tracks")


DEFAULT_MAX_TRACKS_FLOATS: int = 50
DEFAULT_MAX_MARKER_FLOATS: int = 5_000


def get_max_tracks_floats() -> int:
    """Return maximum float count for full trajectory track display."""
    val = os.getenv("SIQVA_MAX_TRACKS_FLOATS")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MAX_TRACKS_FLOATS


def get_max_marker_floats() -> int:
    """Return maximum float count for marker display before switching to coarse density grid."""
    val = os.getenv("SIQVA_MAX_MARKER_FLOATS")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MAX_MARKER_FLOATS


def render_index_overview_map(
    index: Any,
    spec: Any,
    max_tracks: Optional[int] = None,
    max_markers: Optional[int] = None,
) -> tuple[go.Figure, float, str]:
    """Render an overview map of Argo floats directly from the local float index.

    Supports:
        - Float trajectory tracks for up to max_tracks floats.
        - Point markers at last observed position for up to max_markers floats.
        - Coarse grid count aggregation with Scattergeo markers above max_markers floats.

    Hover info:
        Float WMO, last observation date, cycle, and institution.

    Returns:
        (fig, render_time_s, display_mode_description)
    """
    t0 = time.monotonic()
    limit_tracks = max_tracks if max_tracks is not None else get_max_tracks_floats()
    limit_markers = max_markers if max_markers is not None else get_max_marker_floats()

    target_loc = getattr(spec, "basin", None) or getattr(spec, "region", None)
    date_range = getattr(spec, "date_range", None)

    fig = go.Figure()
    last_pos = index.last_positions(bbox_or_basin=target_loc, date_range=date_range)
    total_profiles = index.count_profiles(bbox_or_basin=target_loc, date_range=date_range)
    float_count = len(last_pos)

    if float_count == 0:
        fig.add_annotation(
            text="No active Argo floats found in this region and period.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        display_mode = "No active floats matching query bounds."
    elif float_count <= limit_tracks:
        # 1. Trajectory tracks for small float counts
        tracks_df = index.tracks(bbox_or_basin=target_loc, date_range=date_range)
        for wmo, group in tracks_df.groupby("wmo"):
            sorted_g = group.sort_values("date")
            custom_data = sorted_g[["wmo", "date", "cycle", "institution"]].astype(str).values
            fig.add_trace(
                go.Scattergeo(
                    lon=sorted_g["longitude"],
                    lat=sorted_g["latitude"],
                    mode="lines+markers",
                    name=f"WMO {wmo}",
                    line=dict(width=1.5, color=COLOR_PRIMARY_TEAL),
                    marker=dict(size=5, color=COLOR_PRIMARY_TEAL),
                    customdata=custom_data,
                    hovertemplate=(
                        "Float: %{customdata[0]}<br>"
                        "Date: %{customdata[1]}<br>"
                        "Cycle: %{customdata[2]}<br>"
                        "Institution: %{customdata[3]}<extra></extra>"
                    ),
                    showlegend=float_count <= 15,
                )
            )
        display_mode = f"Showing full trajectory tracks for {float_count} active floats."
    elif float_count <= limit_markers:
        # 2. Markers at last known position
        custom_data = last_pos[["wmo", "date", "cycle", "institution"]].astype(str).values
        fig.add_trace(
            go.Scattergeo(
                lon=last_pos["longitude"],
                lat=last_pos["latitude"],
                mode="markers",
                name="Last Position",
                marker=dict(size=6, color=COLOR_PRIMARY_TEAL, opacity=0.8),
                customdata=custom_data,
                hovertemplate=(
                    "Float: %{customdata[0]}<br>"
                    "Last Date: %{customdata[1]}<br>"
                    "Cycle: %{customdata[2]}<br>"
                    "Institution: %{customdata[3]}<extra></extra>"
                ),
                showlegend=False,
            )
        )
        display_mode = f"Showing last observed positions for {float_count:,} active floats (tracks hidden above {limit_tracks} floats)."
    else:
        # 3. Coarse grid aggregation for > 5,000 floats
        grid_deg = 5.0
        lat_bin = ((last_pos["latitude"] + 90.0) // grid_deg) * grid_deg - 90.0 + (grid_deg / 2.0)
        lon_bin = ((last_pos["longitude"] + 180.0) // grid_deg) * grid_deg - 180.0 + (grid_deg / 2.0)
        grid_df = last_pos.copy()
        grid_df["lat_bin"] = lat_bin
        grid_df["lon_bin"] = lon_bin
        aggregated = grid_df.groupby(["lat_bin", "lon_bin"]).agg(
            float_count=("wmo", "nunique"),
            cycle_max=("cycle", "max"),
        ).reset_index()

        max_bin_count = aggregated["float_count"].max() if not aggregated.empty else 1
        sizes = 8 + (aggregated["float_count"] / max_bin_count) * 22
        custom_data = aggregated[["float_count", "cycle_max"]].values

        fig.add_trace(
            go.Scattergeo(
                lon=aggregated["lon_bin"],
                lat=aggregated["lat_bin"],
                mode="markers",
                name="Float Density",
                marker=dict(
                    size=sizes,
                    color=aggregated["float_count"],
                    colorscale="Teal",
                    colorbar=dict(title="Floats"),
                    opacity=0.85,
                    showscale=True,
                ),
                customdata=custom_data,
                hovertemplate=(
                    "Grid Cell: %{lat:.1f}°, %{lon:.1f}°<br>"
                    "Active Floats: %{customdata[0]:,}<br>"
                    "Max Cycle: %{customdata[1]}<extra></extra>"
                ),
                showlegend=False,
            )
        )
        display_mode = f"Aggregated into 5° spatial density grid for {float_count:,} active floats (density grid active above {limit_markers:,} floats)."

    fig.update_geos(
        projection_type="natural earth",
        showland=True,
        landcolor="#12303F",
        showocean=True,
        oceancolor="#0B1F2A",
        showcountries=True,
        countrycolor="#1E4558",
        coastlinecolor="#1E4558",
        bgcolor=THEME_BG,
    )

    basin_name = getattr(spec, "basin", None)
    region_bbox = getattr(spec, "region", None)
    from .gazetteer import KNOWN_REGIONS
    region_label = basin_name or (next((name for name, b in KNOWN_REGIONS.items() if b == region_bbox), None) or "Region")
    fig_title = f"Argo Float Positions \u2014 {region_label} ({float_count:,} floats, {total_profiles:,} profiles)"
    apply_theme(fig, title=fig_title)

    t1 = time.monotonic()
    render_time_s = t1 - t0
    return fig, render_time_s, display_mode


def _filter_profile(df: Optional[pd.DataFrame], summary: Any) -> pd.DataFrame:
    """Filter DataFrame to single profile specified by summary, ensuring normalized columns and depth."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    sub = df.copy()

    # Column normalization
    if "PLATFORM_NUMBER" in sub.columns and "wmo_id" not in sub.columns:
        sub["wmo_id"] = sub["PLATFORM_NUMBER"]
    if "CYCLE_NUMBER" in sub.columns and "cycle" not in sub.columns:
        sub["cycle"] = sub["CYCLE_NUMBER"]
    if "TEMP" in sub.columns and "temp" not in sub.columns:
        sub["temp"] = sub["TEMP"]
    if "PSAL" in sub.columns and "psal" not in sub.columns:
        sub["psal"] = sub["PSAL"]
    if "PRES" in sub.columns and "pres" not in sub.columns:
        sub["pres"] = sub["PRES"]
    if "LATITUDE" in sub.columns and "lat" not in sub.columns:
        sub["lat"] = sub["LATITUDE"]
    if "LONGITUDE" in sub.columns and "lon" not in sub.columns:
        sub["lon"] = sub["LONGITUDE"]

    wmo = summary.get("wmo_id") if hasattr(summary, "get") else getattr(summary, "wmo_id", None)
    cycle = summary.get("cycle") if hasattr(summary, "get") else getattr(summary, "cycle", None)

    if "wmo_id" in sub.columns and wmo is not None:
        sub = sub[sub["wmo_id"].astype(str) == str(wmo)]
    if "cycle" in sub.columns and cycle is not None:
        sub = sub[sub["cycle"] == cycle]

    # Ensure depth_m exists
    if "depth_m" not in sub.columns and "pres" in sub.columns:
        lat_val = float(sub["lat"].iloc[0]) if "lat" in sub.columns and len(sub) else 0.0
        p_arr = pd.to_numeric(sub["pres"], errors="coerce").to_numpy(dtype=float)
        if gsw is not None:
            try:
                sub["depth_m"] = -gsw.z_from_p(p_arr, lat_val)
            except Exception:
                sub["depth_m"] = p_arr
        else:
            sub["depth_m"] = p_arr

    if "depth_m" in sub.columns:
        return sub.sort_values("depth_m").drop_duplicates(subset=["depth_m"])
    return sub


def plot_thermocline_and_barrier(
    df: Optional[pd.DataFrame],
    summary: Any,
    title: Optional[str] = None,
) -> go.Figure:
    """Plot Temperature vs Depth with Density MLD, Temp ILD, and shaded Barrier Layer."""
    fig = go.Figure()
    if gsw is None:
        fig.add_annotation(
            text="TEOS-10 physics plot requires 'gsw' library, which is not installed.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Thermocline & Barrier Layer Structure")
    prof = _filter_profile(df, summary)

    if prof.empty or "temp" not in prof.columns:
        fig.add_annotation(
            text="No profile observations available for thermocline display.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Thermocline & Barrier Layer Structure")

    sub = prof[prof["depth_m"] <= 300.0] if "depth_m" in prof.columns else prof

    # Temperature profile trace
    fig.add_trace(
        go.Scatter(
            x=sub["temp"],
            y=sub["depth_m"],
            mode="lines+markers",
            name="Temperature (°C)",
            line=dict(color="#FF8C42", width=2.5),
            marker=dict(size=4, color="#FF8C42"),
        )
    )

    mld = summary.get("mld_dens_m") if hasattr(summary, "get") else getattr(summary, "mld_dens_m", None)
    ild = summary.get("ild_temp_m") if hasattr(summary, "get") else getattr(summary, "ild_temp_m", None)
    blt = summary.get("barrier_layer_m") if hasattr(summary, "get") else getattr(summary, "barrier_layer_m", None)

    # Shaded Barrier Layer if BLT > 0
    if blt is not None and blt > 0 and mld is not None and ild is not None:
        fig.add_hrect(
            y0=mld,
            y1=ild,
            fillcolor="rgba(155, 89, 182, 0.35)",
            line_width=0,
            annotation_text=f"Barrier Layer ({blt} m)",
            annotation_position="top left",
            annotation_font=dict(color="#E6F1F5", size=11),
        )

    # Reference lines for MLD, ILD, Z20
    if mld is not None:
        fig.add_hline(
            y=mld,
            line_dash="dash",
            line_color="#2EC4B6",
            annotation_text=f"Density MLD: {mld} m",
            annotation_position="top right",
            annotation_font=dict(color="#2EC4B6", size=11),
        )

    if ild is not None:
        fig.add_hline(
            y=ild,
            line_dash="dash",
            line_color="#FFB703",
            annotation_text=f"Temp ILD: {ild} m",
            annotation_position="bottom right",
            annotation_font=dict(color="#FFB703", size=11),
        )

    z20 = summary.get("z20_isotherm_m") if hasattr(summary, "get") else getattr(summary, "z20_isotherm_m", None)
    if z20 is not None:
        fig.add_hline(
            y=z20,
            line_dash="dot",
            line_color="#06D6A0",
            annotation_text=f"Z20 Thermocline: {z20} m",
            annotation_position="top right",
            annotation_font=dict(color="#06D6A0", size=11),
        )

    profile_label = summary.get("profile_id", "Profile") if hasattr(summary, "get") else getattr(summary, "profile_id", "Profile")
    fig.update_layout(
        xaxis=dict(title="Temperature (°C)"),
        yaxis=dict(
            title="Depth (m)",
            autorange="reversed",
            range=[min(300.0, float(prof["depth_m"].max()) if len(prof) else 300.0), 0],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return apply_theme(fig, title=title or f"Thermocline & Barrier Layer Structure — {profile_label}")


def plot_cyclone_tchp(
    df: Optional[pd.DataFrame],
    summary: Any,
    title: Optional[str] = None,
) -> go.Figure:
    """Plot Temperature vs Depth with shaded contiguous upper layer > 26°C for TCHP."""
    fig = go.Figure()
    if gsw is None:
        fig.add_annotation(
            text="TEOS-10 physics plot requires 'gsw' library, which is not installed.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Tropical Cyclone Heat Potential (TCHP)")
    prof = _filter_profile(df, summary)

    if prof.empty or "temp" not in prof.columns:
        fig.add_annotation(
            text="No profile observations available for cyclone TCHP display.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "Tropical Cyclone Heat Potential (TCHP)")

    sub = prof[prof["depth_m"] <= 200.0] if "depth_m" in prof.columns else prof

    z26 = summary.get("z26_isotherm_m") if hasattr(summary, "get") else getattr(summary, "z26_isotherm_m", None)
    tchp = summary.get("tchp_kj_cm2", 0.0) if hasattr(summary, "get") else getattr(summary, "tchp_kj_cm2", 0.0)

    # Shaded contiguous layer between T(z) and 26°C from surface down to z26
    if z26 is not None and z26 > 0:
        layer = sub[sub["depth_m"] < z26]
        z_pts = np.append(layer["depth_m"].to_numpy(dtype=float), float(z26))
        t_pts = np.maximum(np.append(layer["temp"].to_numpy(dtype=float), 26.0), 26.0)

        x_poly = np.concatenate([t_pts, np.full_like(z_pts, 26.0)])
        y_poly = np.concatenate([z_pts, z_pts[::-1]])

        fig.add_trace(
            go.Scatter(
                x=x_poly,
                y=y_poly,
                fill="toself",
                fillcolor="rgba(255, 107, 107, 0.35)",
                line=dict(color="rgba(255, 255, 255, 0)"),
                name=f"TCHP Integrated Area ({tchp} kJ/cm²)",
                hoverinfo="skip",
            )
        )

    # Temperature profile trace
    fig.add_trace(
        go.Scatter(
            x=sub["temp"],
            y=sub["depth_m"],
            mode="lines+markers",
            name="Temperature (°C)",
            line=dict(color="#FF8C42", width=2.5),
            marker=dict(size=4, color="#FF8C42"),
        )
    )

    # 26°C vertical threshold line
    fig.add_vline(
        x=26.0,
        line_dash="dash",
        line_color="#FF6B6B",
        annotation_text="26°C Isotherm",
        annotation_position="top left",
        annotation_font=dict(color="#FF6B6B", size=11),
    )

    # Z26 horizontal depth line
    if z26 is not None:
        fig.add_hline(
            y=z26,
            line_dash="dot",
            line_color="#FF8C42",
            annotation_text=f"Z26: {z26} m",
            annotation_position="bottom right",
            annotation_font=dict(color="#FF8C42", size=11),
        )

    profile_label = summary.get("profile_id", "Profile") if hasattr(summary, "get") else getattr(summary, "profile_id", "Profile")
    fig.update_layout(
        xaxis=dict(title="Temperature (°C)"),
        yaxis=dict(
            title="Depth (m)",
            autorange="reversed",
            range=[min(200.0, float(prof["depth_m"].max()) if len(prof) else 200.0), 0],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return apply_theme(fig, title=title or f"Tropical Cyclone Heat Potential (TCHP: {tchp} kJ/cm²) — {profile_label}")


def plot_acoustic_profile(
    df: Optional[pd.DataFrame],
    summary: Any,
    title: Optional[str] = None,
) -> go.Figure:
    """Plot TEOS-10 sound speed profile vs depth, marking SLD and SOFAR channel axis."""
    fig = go.Figure()
    if gsw is None:
        fig.add_annotation(
            text="TEOS-10 physics plot requires 'gsw' library, which is not installed.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "TEOS-10 Acoustic Sound Speed Profile")
    prof = _filter_profile(df, summary)

    if prof.empty or "sound_speed" not in prof.columns:
        fig.add_annotation(
            text="No sound speed observations available for acoustic display.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=THEME_TEXT, size=14),
        )
        return apply_theme(fig, title=title or "TEOS-10 Acoustic Sound Speed Profile")

    # Sound speed profile trace
    fig.add_trace(
        go.Scatter(
            x=prof["sound_speed"],
            y=prof["depth_m"],
            mode="lines",
            name="Sound Speed (m/s)",
            line=dict(color="#2EC4B6", width=2.5),
        )
    )

    # Mark SLD
    sld = summary.get("sld_m") if hasattr(summary, "get") else getattr(summary, "sld_m", None)
    if sld is not None:
        snd_sld = float(np.interp(sld, prof["depth_m"], prof["sound_speed"]))
        fig.add_hline(
            y=sld,
            line_dash="dash",
            line_color="#17BECF",
            annotation_text=f"SLD Peak: {sld} m ({snd_sld:.1f} m/s)",
            annotation_position="top right",
            annotation_font=dict(color="#17BECF", size=11),
        )
        fig.add_trace(
            go.Scatter(
                x=[snd_sld],
                y=[sld],
                mode="markers",
                marker=dict(size=10, color="#17BECF", symbol="diamond"),
                name=f"Sonic Layer Depth ({sld} m)",
            )
        )

    # Mark SOFAR channel axis
    sofar = summary.get("sofar_axis_m") if hasattr(summary, "get") else getattr(summary, "sofar_axis_m", None)
    if sofar is not None:
        snd_sofar = float(np.interp(sofar, prof["depth_m"], prof["sound_speed"]))
        fig.add_hline(
            y=sofar,
            line_dash="dash",
            line_color="#A78BFA",
            annotation_text=f"SOFAR Axis: {sofar} m ({snd_sofar:.1f} m/s)",
            annotation_position="bottom right",
            annotation_font=dict(color="#A78BFA", size=11),
        )
        fig.add_trace(
            go.Scatter(
                x=[snd_sofar],
                y=[sofar],
                mode="markers",
                marker=dict(size=10, color="#A78BFA", symbol="star"),
                name=f"SOFAR Axis ({sofar} m)",
            )
        )

    profile_label = summary.get("profile_id", "Profile") if hasattr(summary, "get") else getattr(summary, "profile_id", "Profile")
    fig.update_layout(
        xaxis=dict(title="Sound Speed (m/s)"),
        yaxis=dict(title="Depth (m)", autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return apply_theme(fig, title=title or f"TEOS-10 Acoustic Sound Speed Profile — {profile_label}")


# ==============================================================================
# Shared Oceanic / Retro-Terminal Theme Helper
# ==============================================================================
def _apply_siqva_theme(
    fig: go.Figure,
    title: str,
    xaxis_title: str,
    yaxis_title: str,
    invert_y: bool = True
) -> go.Figure:
    """Apply SIQVA retro-terminal theme styling to a Plotly figure."""
    fig.update_layout(
        title=dict(text=title, font=dict(family="Courier New, monospace", size=16, color="#00F0FF")),
        paper_bgcolor="#070F1A",
        plot_bgcolor="#0B192C",
        font=dict(family="Courier New, monospace", color="#B8D8E8", size=12),
        xaxis=dict(title=xaxis_title, gridcolor="#1A324C", zerolinecolor="#1A324C"),
        yaxis=dict(
            title=yaxis_title,
            gridcolor="#1A324C",
            zerolinecolor="#1A324C",
            autorange="reversed" if invert_y else True
        ),
        hovermode="closest",
        margin=dict(l=60, r=40, t=60, b=50),
        legend=dict(bgcolor="rgba(11, 25, 44, 0.8)", bordercolor="#00F0FF", borderwidth=1)
    )
    return fig


# ==============================================================================
# 1. [TIME // HOV] Hovmöller Diagram (Depth vs. Time Contour)
# ==============================================================================
def plot_hovmoller_section(
    df: Optional[pd.DataFrame],
    param: str = "TEMP",
    max_depth: float = 1000.0,
    title: Optional[str] = None
) -> go.Figure:
    """
    Plots a 2D Time vs. Depth (Pressure) interpolated contour chart for a single float
    or regional time series to reveal seasonal thermocline shoaling/deepening or Rossby waves.
    Expected columns: ['TIME', 'PRES', param]
    """
    fig = go.Figure()

    if df is None or len(df) == 0:
        fig.add_annotation(
            text="No observation data available for Hovmöller section.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or f"[TIME // HOV] Hovmöller Temporal Evolution ({param})",
            xaxis_title="Observation Date / Cycle Time",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    # Normalize column names if lower-case
    sub = df.copy()
    col_map = {c.upper(): c for c in sub.columns}
    time_col = col_map.get("TIME", "TIME" if "TIME" in sub.columns else None)
    pres_col = col_map.get("PRES", "PRES" if "PRES" in sub.columns else ("depth_m" if "depth_m" in sub.columns else None))
    param_col = col_map.get(param.upper(), param if param in sub.columns else None)

    if not time_col or not pres_col or not param_col or time_col not in sub.columns or pres_col not in sub.columns or param_col not in sub.columns:
        fig.add_annotation(
            text=f"Hovmöller section requires TIME, PRES, and {param} columns in dataset.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLOR_AMBER, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or f"[TIME // HOV] Hovmöller Temporal Evolution ({param})",
            xaxis_title="Observation Date / Cycle Time",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    df_clean = sub.dropna(subset=[time_col, pres_col, param_col]).copy()
    df_clean = df_clean[df_clean[pres_col] <= max_depth]

    if df_clean.empty:
        fig.add_annotation(
            text=f"No valid observations found within 0–{max_depth:.0f} dbar.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or f"[TIME // HOV] Hovmöller Temporal Evolution ({param})",
            xaxis_title="Observation Date / Cycle Time",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    df_clean["TIME_DT"] = pd.to_datetime(df_clean[time_col])
    df_clean = df_clean.sort_values(["TIME_DT", pres_col])

    unique_times = np.sort(df_clean["TIME_DT"].unique())

    if len(unique_times) < 2:
        # Fallback to scatter if only one timestamp
        fig.add_trace(go.Scatter(
            x=df_clean[param_col],
            y=df_clean[pres_col],
            mode="lines+markers",
            line=dict(color="#00F0FF", width=2),
            name=f"{param} Profile"
        ))
        return _apply_siqva_theme(
            fig,
            title=title or f"[TIME // HOV] Single-Cycle Profile ({param})",
            xaxis_title=f"{param}",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    depth_grid = np.linspace(5, max_depth, 100)
    z_matrix = np.full((len(depth_grid), len(unique_times)), np.nan)

    for j, t in enumerate(unique_times):
        cycle_df = df_clean[df_clean["TIME_DT"] == t].sort_values(pres_col)
        if len(cycle_df) >= 2:
            z_matrix[:, j] = np.interp(
                depth_grid,
                cycle_df[pres_col].values,
                cycle_df[param_col].values,
                left=np.nan,
                right=np.nan
            )

    colorscale = "Thermal" if "TEMP" in param.upper() else "Haline"
    unit = "°C" if "TEMP" in param.upper() else ("PSU" if "PSAL" in param.upper() else "")

    fig.add_trace(go.Contour(
        z=z_matrix,
        x=unique_times,
        y=depth_grid,
        colorscale=colorscale,
        colorbar=dict(title=f"{param} ({unit})"),
        contours=dict(coloring="heatmap", showlabels=True, labelfont=dict(size=10, color="white")),
        hovertemplate="Date: %{x}<br>Depth: %{y:.1f} m<br>" + f"{param}: %{{z:.2f}} {unit}<extra></extra>"
    ))

    return _apply_siqva_theme(
        fig,
        title=title or f"[TIME // HOV] Hovmöller Temporal Evolution ({param})",
        xaxis_title="Observation Date / Cycle Time",
        yaxis_title="Depth / Pressure (dbar)",
        invert_y=True
    )


# ==============================================================================
# 2. [TEOS-10 // N2] Brunt-Väisälä Buoyancy Frequency & Water Column Stability
# ==============================================================================
def plot_stability_buoyancy(
    pres: Any,
    temp: Any = None,
    psal: Any = None,
    lat: float = 0.0,
    lon: float = 0.0,
    title: Optional[str] = None
) -> go.Figure:
    """
    Calculates TEOS-10 Brunt-Väisälä Frequency Squared (N^2) and Potential Density Anomaly (sigma0).
    Identifies the pycnocline core (maximum stratification) and static instabilities (N^2 < 0).
    Accepts either (pres_array, temp_array, psal_array, lat, lon) or (df, lat=..., lon=...).
    """
    fig = go.Figure()

    if gsw is None:
        fig.add_annotation(
            text="TEOS-10 GSW library is not available in environment.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLOR_AMBER, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[TEOS-10 // N2] Stratification & Brunt-Väisälä Frequency (N²)",
            xaxis_title="Buoyancy Frequency Squared N² (×10⁻⁴ s⁻²)",
            yaxis_title="Mid-Point Pressure / Depth (dbar)",
            invert_y=True
        )

    # Handle DataFrame input
    if isinstance(pres, pd.DataFrame):
        df_in = pres
        if df_in.empty:
            fig.add_annotation(
                text="No observation data available for buoyancy calculation.",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(color=THEME_TEXT, size=14)
            )
            return _apply_siqva_theme(
                fig,
                title=title or "[TEOS-10 // N2] Stratification & Brunt-Väisälä Frequency (N²)",
                xaxis_title="Buoyancy Frequency Squared N² (×10⁻⁴ s⁻²)",
                yaxis_title="Mid-Point Pressure / Depth (dbar)",
                invert_y=True
            )
        col_pres = "PRES" if "PRES" in df_in.columns else ("pres" if "pres" in df_in.columns else ("depth_m" if "depth_m" in df_in.columns else None))
        col_temp = "TEMP" if "TEMP" in df_in.columns else ("temp" if "temp" in df_in.columns else None)
        col_psal = "PSAL" if "PSAL" in df_in.columns else ("psal" if "psal" in df_in.columns else None)

        if not col_pres or not col_temp or not col_psal:
            fig.add_annotation(
                text="Buoyancy calculation requires PRES, TEMP, and PSAL variables.",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(color=COLOR_AMBER, size=14)
            )
            return _apply_siqva_theme(
                fig,
                title=title or "[TEOS-10 // N2] Stratification & Brunt-Väisälä Frequency (N²)",
                xaxis_title="Buoyancy Frequency Squared N² (×10⁻⁴ s⁻²)",
                yaxis_title="Mid-Point Pressure / Depth (dbar)",
                invert_y=True
            )

        if "LATITUDE" in df_in.columns and lat == 0.0:
            lat = float(df_in["LATITUDE"].dropna().mean()) if not df_in["LATITUDE"].dropna().empty else 0.0
        if "LONGITUDE" in df_in.columns and lon == 0.0:
            lon = float(df_in["LONGITUDE"].dropna().mean()) if not df_in["LONGITUDE"].dropna().empty else 0.0

        p_arr = df_in[col_pres].values
        t_arr = df_in[col_temp].values
        sp_arr = df_in[col_psal].values
    else:
        p_arr = np.asarray(pres)
        t_arr = np.asarray(temp)
        sp_arr = np.asarray(psal)

    mask = ~np.isnan(p_arr) & ~np.isnan(t_arr) & ~np.isnan(sp_arr)
    p, t, sp = p_arr[mask], t_arr[mask], sp_arr[mask]

    if len(p) < 3:
        fig.add_annotation(
            text="Insufficient profile levels (need >= 3 valid levels) for N² gradient.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[TEOS-10 // N2] Stratification & Brunt-Väisälä Frequency (N²)",
            xaxis_title="Buoyancy Frequency Squared N² (×10⁻⁴ s⁻²)",
            yaxis_title="Mid-Point Pressure / Depth (dbar)",
            invert_y=True
        )

    sort_idx = np.argsort(p)
    p, t, sp = p[sort_idx], t[sort_idx], sp[sort_idx]

    try:
        sa = gsw.SA_from_SP(sp, p, lon, lat)
        ct = gsw.CT_from_t(sa, t, p)
        n2, p_mid = gsw.Nsquared(sa, ct, p, lat=lat)
    except Exception as exc:
        fig.add_annotation(
            text=f"TEOS-10 N² calculation failed: {exc}",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLOR_AMBER, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[TEOS-10 // N2] Stratification & Brunt-Väisälä Frequency (N²)",
            xaxis_title="Buoyancy Frequency Squared N² (×10⁻⁴ s⁻²)",
            yaxis_title="Mid-Point Pressure / Depth (dbar)",
            invert_y=True
        )

    # Scale N^2 by 1e4 for readable units (10^-4 s^-2)
    n2_scaled = n2 * 1e4

    fig.add_trace(go.Scatter(
        x=n2_scaled,
        y=p_mid,
        mode="lines",
        name="N² (×10⁻⁴ s⁻²)",
        line=dict(color="#00F0FF", width=2.5),
        hovertemplate="N²: %{x:.2f} ×10⁻⁴ s⁻²<br>Depth: %{y:.1f} dbar<extra></extra>"
    ))

    # Highlight Pycnocline Core (Peak Stratification)
    if len(n2_scaled) > 0 and not np.all(np.isnan(n2_scaled)):
        max_n2_idx = int(np.nanargmax(n2_scaled))
        pycnocline_depth = float(p_mid[max_n2_idx])
        fig.add_hline(
            y=pycnocline_depth,
            line_dash="dash",
            line_color="#FF007F",
            annotation_text=f"Pycnocline Core ({pycnocline_depth:.1f} m)",
            annotation_position="bottom right",
            annotation_font_color="#FF007F"
        )

    # Highlight Static Instability threshold (N^2 = 0)
    fig.add_vline(x=0, line_dash="dot", line_color="#FFB800")

    return _apply_siqva_theme(
        fig,
        title=title or "[TEOS-10 // N2] Stratification & Brunt-Väisälä Frequency (N²)",
        xaxis_title="Buoyancy Frequency Squared N² (×10⁻⁴ s⁻²)",
        yaxis_title="Mid-Point Pressure / Depth (dbar)",
        invert_y=True
    )


# ==============================================================================
# 3. [TEOS-10 // TS-SIGMA] Enhanced T-S Diagram with Isopycnal (σ₀) Contours & Spiciness
# ==============================================================================
def plot_ts_with_isopycnals(
    df: Optional[pd.DataFrame],
    lon: float = 80.0,
    lat: float = 15.0,
    title: Optional[str] = None
) -> go.Figure:
    """
    Upgrades a basic T-S diagram by computing a background TEOS-10 potential density (sigma0)
    contour grid and water-mass bounding boxes.
    Expected columns: ['PSAL', 'TEMP', 'PRES']
    """
    fig = go.Figure()

    if df is None or len(df) == 0:
        fig.add_annotation(
            text="No observation data available for T-S isopycnal diagram.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[TEOS-10 // TS-SIGMA] Conservative T-S Diagram with Isopycnals (σ₀)",
            xaxis_title="Absolute Salinity SA (g/kg)",
            yaxis_title="Conservative Temperature Θ (°C)",
            invert_y=False
        )

    if "PSAL" not in df.columns or "TEMP" not in df.columns or "PRES" not in df.columns:
        fig.add_annotation(
            text="T-S diagram requires PSAL, TEMP, and PRES columns in dataset.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLOR_AMBER, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[TEOS-10 // TS-SIGMA] Conservative T-S Diagram with Isopycnals (σ₀)",
            xaxis_title="Absolute Salinity SA (g/kg)",
            yaxis_title="Conservative Temperature Θ (°C)",
            invert_y=False
        )

    df_clean = df.dropna(subset=["PSAL", "TEMP", "PRES"]).copy()
    if df_clean.empty:
        fig.add_annotation(
            text="No valid non-null PSAL, TEMP, PRES observations.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[TEOS-10 // TS-SIGMA] Conservative T-S Diagram with Isopycnals (σ₀)",
            xaxis_title="Absolute Salinity SA (g/kg)",
            yaxis_title="Conservative Temperature Θ (°C)",
            invert_y=False
        )

    total_obs = len(df_clean)
    sampled_df = _stratified_sample_observations(df_clean, max_points=MAX_PLOT_OBSERVATIONS)
    is_sampled = len(sampled_df) < total_obs
    ScatterTrace = getattr(go, "Scattergl", go.Scatter)

    if "LATITUDE" in df_clean.columns and lat == 15.0:
        lat = float(df_clean["LATITUDE"].dropna().mean()) if not df_clean["LATITUDE"].dropna().empty else 15.0
    if "LONGITUDE" in df_clean.columns and lon == 80.0:
        lon = float(df_clean["LONGITUDE"].dropna().mean()) if not df_clean["LONGITUDE"].dropna().empty else 80.0

    if gsw is not None:
        try:
            sa_full = gsw.SA_from_SP(df_clean["PSAL"].values, df_clean["PRES"].values, lon, lat)
            ct_full = gsw.CT_from_t(sa_full, df_clean["TEMP"].values, df_clean["PRES"].values)

            s_min = max(25.0, float(np.nanmin(sa_full)) - 0.5)
            s_max = min(42.0, float(np.nanmax(sa_full)) + 0.5)
            t_min = max(-2.0, float(np.nanmin(ct_full)) - 2.0)
            t_max = min(35.0, float(np.nanmax(ct_full)) + 2.0)

            s_grid = np.linspace(s_min, s_max, 80)
            t_grid = np.linspace(t_min, t_max, 80)
            S_mesh, T_mesh = np.meshgrid(s_grid, t_grid)
            sigma0_mesh = gsw.sigma0(S_mesh, T_mesh)

            # Background Isopycnals (sigma0 lines)
            fig.add_trace(go.Contour(
                x=s_grid,
                y=t_grid,
                z=sigma0_mesh,
                contours=dict(coloring="none", showlabels=True, labelfont=dict(size=10, color="#5C85A6")),
                line=dict(color="#2D4F6C", width=1, dash="dot"),
                showscale=False,
                name="σ₀ (kg/m³)",
                hoverinfo="skip"
            ))

            sa_sampled = gsw.SA_from_SP(sampled_df["PSAL"].values, sampled_df["PRES"].values, lon, lat)
            ct_sampled = gsw.CT_from_t(sa_sampled, sampled_df["TEMP"].values, sampled_df["PRES"].values)

            # Actual observations
            fig.add_trace(ScatterTrace(
                x=sa_sampled,
                y=ct_sampled,
                mode="markers",
                marker=dict(
                    size=5,
                    color=sampled_df["PRES"],
                    colorscale="Viridis_r",
                    colorbar=dict(title="Depth (dbar)"),
                    showscale=True
                ),
                name="Float Profile",
                hovertemplate="SA: %{x:.2f} g/kg<br>CT: %{y:.2f} °C<br>Depth: %{marker.color:.0f} dbar<extra></extra>"
            ))

            if is_sampled:
                fig.add_annotation(
                    text=f"Showing {len(sampled_df):,} of {total_obs:,} observations (sampled)",
                    xref="paper",
                    yref="paper",
                    x=0.02,
                    y=0.98,
                    xanchor="left",
                    yanchor="top",
                    showarrow=False,
                    font=dict(color=THEME_TEXT, size=11),
                    bgcolor="rgba(10, 25, 40, 0.7)",
                    bordercolor=THEME_GRID,
                    borderwidth=1,
                )

            return _apply_siqva_theme(
                fig,
                title=title or "[TEOS-10 // TS-SIGMA] Conservative T-S Diagram with Isopycnals (σ₀)",
                xaxis_title="Absolute Salinity SA (g/kg)",
                yaxis_title="Conservative Temperature Θ (°C)",
                invert_y=False
            )
        except Exception:
            pass

    # Fallback to standard T-S
    fig.add_trace(ScatterTrace(
        x=sampled_df["PSAL"],
        y=sampled_df["TEMP"],
        mode="markers",
        marker=dict(
            size=5,
            color=sampled_df["PRES"],
            colorscale="Viridis",
            colorbar=dict(title="Depth (dbar)"),
            showscale=True
        ),
        name="T-S Observations",
        hovertemplate="Salinity: %{x:.2f}<br>Temp: %{y:.2f} °C<br>Depth: %{marker.color:.0f} dbar<extra></extra>"
    ))

    if is_sampled:
        fig.add_annotation(
            text=f"Showing {len(sampled_df):,} of {total_obs:,} observations (sampled)",
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.98,
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font=dict(color=THEME_TEXT, size=11),
            bgcolor="rgba(10, 25, 40, 0.7)",
            bordercolor=THEME_GRID,
            borderwidth=1,
        )

    return _apply_siqva_theme(
        fig,
        title=title or "[TEMP // PSAL] Temperature-Salinity Diagram",
        xaxis_title="Practical Salinity (PSAL)",
        yaxis_title="Temperature (°C)",
        invert_y=False
    )


# ==============================================================================
# 4. [STAT // ENVELOPE] Regional Anomaly & Climatological Envelope Plot
# ==============================================================================
def plot_regional_climatology_envelope(
    df_region: Optional[pd.DataFrame],
    target_wmo: str | int | None = None,
    param: str = "TEMP",
    max_depth: float = 500.0,
    title: Optional[str] = None,
    is_sample: bool = False,
) -> go.Figure:
    """
    Computes the regional mean and ±1 SD shaded envelope across multiple profiles,
    overlaying a specific target profile to detect marine heatwaves or salinity anomalies.

    When is_sample is True, regional aggregate curves (mean line and envelope) are
    suppressed to prevent unrepresentative regional statistics, rendering individual
    per-profile curves only.

    Expected columns: ['PRES', param, 'PLATFORM_NUMBER']
    """
    fig = go.Figure()

    if df_region is None or len(df_region) == 0:
        fig.add_annotation(
            text="No observation data available for regional envelope.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or f"[STAT // ENVELOPE] Regional Mean & ±1σ Spread ({param})",
            xaxis_title=f"{param}",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    col_pres = "PRES" if "PRES" in df_region.columns else ("pres" if "pres" in df_region.columns else None)
    col_param = param if param in df_region.columns else (param.upper() if param.upper() in df_region.columns else None)

    if not col_pres or not col_param:
        fig.add_annotation(
            text=f"Regional envelope requires {param} and PRES columns.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLOR_AMBER, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or f"[STAT // ENVELOPE] Regional Mean & ±1σ Spread ({param})",
            xaxis_title=f"{param}",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    depth_bins = np.arange(0, max_depth + 10, 10)
    df_clean = df_region.dropna(subset=[col_pres, col_param]).copy()
    df_clean = df_clean[df_clean[col_pres] <= max_depth]

    if df_clean.empty:
        fig.add_annotation(
            text="No observations available within specified depth range.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or f"[STAT // ENVELOPE] Regional Mean & ±1σ Spread ({param})",
            xaxis_title=f"{param}",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    plat_col = "PLATFORM_NUMBER" if "PLATFORM_NUMBER" in df_clean.columns else ("wmo_id" if "wmo_id" in df_clean.columns else None)
    cyc_col = "CYCLE_NUMBER" if "CYCLE_NUMBER" in df_clean.columns else None

    if is_sample:
        # Suppress aggregate (mean line and ±1σ envelope); render per-profile curves only
        if plat_col and cyc_col:
            profiles = list(df_clean.groupby([plat_col, cyc_col]))
        elif plat_col:
            profiles = list(df_clean.groupby(plat_col))
        else:
            profiles = [(("Single", "1"), df_clean)]

        for p_id, group in profiles:
            grp = group.dropna(subset=[col_pres, col_param]).sort_values(col_pres)
            if grp.empty:
                continue
            label = f"WMO {p_id[0]} Cyc {p_id[1]}" if isinstance(p_id, tuple) else f"Profile {p_id}"
            fig.add_trace(
                go.Scatter(
                    x=grp[col_param],
                    y=grp[col_pres],
                    mode="lines",
                    name=label,
                    line=dict(width=1.5),
                    opacity=0.7,
                )
            )

        fig.add_annotation(
            text="Sample selection: regional mean and envelope suppressed; showing individual profiles only.",
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.98,
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font=dict(color=COLOR_AMBER, size=11),
            bgcolor="rgba(10, 25, 40, 0.7)",
            bordercolor=THEME_GRID,
            borderwidth=1,
        )
    else:
        df_clean["DEPTH_BIN"] = pd.cut(df_clean[col_pres], bins=depth_bins, labels=depth_bins[:-1] + 5)
        stats = df_clean.groupby("DEPTH_BIN", observed=True)[col_param].agg(["mean", "std"]).dropna().reset_index()

        depths = stats["DEPTH_BIN"].astype(float).values
        mean_val = stats["mean"].values
        std_val = stats["std"].fillna(0).values

        if len(depths) > 0:
            # ±1 Standard Deviation Shaded Envelope
            fig.add_trace(go.Scatter(
                x=np.concatenate([mean_val + std_val, (mean_val - std_val)[::-1]]),
                y=np.concatenate([depths, depths[::-1]]),
                fill="toself",
                fillcolor="rgba(0, 240, 255, 0.18)",
                line=dict(color="rgba(255,255,255,0)"),
                name="Regional ±1σ Envelope",
                hoverinfo="skip"
            ))

            # Regional Mean Curve
            fig.add_trace(go.Scatter(
                x=mean_val,
                y=depths,
                mode="lines",
                line=dict(color="#00F0FF", width=2, dash="dash"),
                name="Regional Mean"
            ))

        # Optional Target Float Profile Overlay
        if target_wmo is not None and plat_col:
            target_df = df_clean[df_clean[plat_col].astype(str) == str(target_wmo)].sort_values(col_pres)
            if not target_df.empty:
                fig.add_trace(go.Scatter(
                    x=target_df[col_param],
                    y=target_df[col_pres],
                    mode="lines",
                    line=dict(color="#FF3366", width=3),
                    name=f"Float {target_wmo} (Target)"
                ))

    unit = "°C" if "TEMP" in param.upper() else ("PSU" if "PSAL" in param.upper() else "")
    default_title = (
        f"Individual Profiles ({param}) [Sample: Regional Aggregates Suppressed]"
        if is_sample
        else f"[STAT // ENVELOPE] Regional Mean, ±1σ Spread & Anomaly ({param})"
    )
    return _apply_siqva_theme(
        fig,
        title=title or default_title,
        xaxis_title=f"{param} ({unit})",
        yaxis_title="Depth / Pressure (dbar)",
        invert_y=True
    )


# ==============================================================================
# 5. [BGC // OMZ] Dissolved Oxygen & Hypoxic Habitat Compression Profile
# ==============================================================================
def plot_bgc_omz_profile(
    pres: Any,
    doxy: Any = None,
    temp: Any = None,
    title: Optional[str] = None
) -> go.Figure:
    """
    Plots BGC-Argo Dissolved Oxygen (μmol/kg) against depth, highlighting the
    Hypoxic Threshold (< 60 μmol/kg) and Suboxic / Severe OMZ Core (< 20 μmol/kg).
    Accepts either (pres_array, doxy_array) or (df).
    """
    fig = go.Figure()

    if isinstance(pres, pd.DataFrame):
        df_in = pres
        if df_in.empty:
            fig.add_annotation(
                text="No observation data available for oxygen profile.",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(color=THEME_TEXT, size=14)
            )
            return _apply_siqva_theme(
                fig,
                title=title or "[BGC // OMZ] Dissolved Oxygen & Oxygen Minimum Zone (OMZ)",
                xaxis_title="Dissolved Oxygen DOXY (μmol/kg)",
                yaxis_title="Depth / Pressure (dbar)",
                invert_y=True
            )
        col_pres = "PRES" if "PRES" in df_in.columns else ("pres" if "pres" in df_in.columns else ("depth_m" if "depth_m" in df_in.columns else None))
        col_doxy = "DOXY" if "DOXY" in df_in.columns else ("doxy" if "doxy" in df_in.columns else ("OXYGEN" if "OXYGEN" in df_in.columns else None))

        if not col_doxy or not col_pres:
            fig.add_annotation(
                text="BGC-Argo DOXY (Dissolved Oxygen) observations not present in this dataset.",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(color=COLOR_AMBER, size=13)
            )
            return _apply_siqva_theme(
                fig,
                title=title or "[BGC // OMZ] Dissolved Oxygen & Oxygen Minimum Zone (OMZ)",
                xaxis_title="Dissolved Oxygen DOXY (μmol/kg)",
                yaxis_title="Depth / Pressure (dbar)",
                invert_y=True
            )
        p_arr = df_in[col_pres].values
        ox_arr = df_in[col_doxy].values
    else:
        p_arr = np.asarray(pres)
        ox_arr = np.asarray(doxy) if doxy is not None else np.array([])

    if len(p_arr) == 0 or len(ox_arr) == 0:
        fig.add_annotation(
            text="No DOXY observations available to plot.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[BGC // OMZ] Dissolved Oxygen & Oxygen Minimum Zone (OMZ)",
            xaxis_title="Dissolved Oxygen DOXY (μmol/kg)",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    mask = ~np.isnan(p_arr) & ~np.isnan(ox_arr)
    p, ox = p_arr[mask], ox_arr[mask]

    if len(p) == 0:
        fig.add_annotation(
            text="No valid non-null DOXY observations.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[BGC // OMZ] Dissolved Oxygen & Oxygen Minimum Zone (OMZ)",
            xaxis_title="Dissolved Oxygen DOXY (μmol/kg)",
            yaxis_title="Depth / Pressure (dbar)",
            invert_y=True
        )

    sort_idx = np.argsort(p)
    p, ox = p[sort_idx], ox[sort_idx]

    # Shaded Hypoxic Risk Zone (< 60 umol/kg)
    fig.add_vrect(
        x0=0, x1=60,
        fillcolor="rgba(255, 51, 102, 0.15)",
        layer="below",
        line_width=0,
        annotation_text="Hypoxic Zone (<60 μmol/kg)",
        annotation_position="top left",
        annotation_font_color="#FF3366"
    )

    # Dissolved Oxygen Profile
    fig.add_trace(go.Scatter(
        x=ox,
        y=p,
        mode="lines+markers",
        marker=dict(size=4),
        line=dict(color="#39FF14", width=2.5),
        name="Dissolved O₂"
    ))

    # Find OMZ ceiling (first depth where DOXY drops below 60 umol/kg)
    hypoxic_indices = np.where(ox < 60.0)[0]
    if len(hypoxic_indices) > 0:
        omz_ceiling = float(p[hypoxic_indices[0]])
        fig.add_hline(
            y=omz_ceiling,
            line_dash="dash",
            line_color="#FFB800",
            annotation_text=f"OMZ Ceiling / Habitable Floor ({omz_ceiling:.1f} m)",
            annotation_font_color="#FFB800"
        )

    return _apply_siqva_theme(
        fig,
        title=title or "[BGC // OMZ] Dissolved Oxygen & Oxygen Minimum Zone (OMZ)",
        xaxis_title="Dissolved Oxygen DOXY (μmol/kg)",
        yaxis_title="Depth / Pressure (dbar)",
        invert_y=True
    )


# ==============================================================================
# 6. [DYN // DRIFT] Lagrangian Trajectory Drift Speed & Eddy Detection Time Series
# ==============================================================================
def plot_float_drift_velocity(
    df_track: Optional[pd.DataFrame],
    target_wmo: str | int | None = None,
    title: Optional[str] = None
) -> go.Figure:
    """
    Calculates cycle-to-cycle surface/parking drift velocity (cm/s) using great-circle
    distance (`gsw.distance`) between consecutive Argo surfacing positions.
    High spikes (> 30 cm/s) indicate entrainment in boundary currents or mesoscale eddies.
    Expected columns: ['TIME', 'LATITUDE', 'LONGITUDE', 'CYCLE_NUMBER']
    """
    fig = go.Figure()

    if df_track is None or len(df_track) == 0:
        fig.add_annotation(
            text="No trajectory observations available for drift velocity calculation.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[DYN // DRIFT] Lagrangian Float Drift Velocity (cm/s)",
            xaxis_title="Surfacing Date",
            yaxis_title="Estimated Drift Speed (cm/s)",
            invert_y=False
        )

    col_map = {c.upper(): c for c in df_track.columns}
    time_col = col_map.get("TIME", "TIME" if "TIME" in df_track.columns else None)
    lat_col = col_map.get("LATITUDE", "LATITUDE" if "LATITUDE" in df_track.columns else None)
    lon_col = col_map.get("LONGITUDE", "LONGITUDE" if "LONGITUDE" in df_track.columns else None)

    if not time_col or not lat_col or not lon_col:
        fig.add_annotation(
            text="Drift velocity requires TIME, LATITUDE, and LONGITUDE columns.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLOR_AMBER, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[DYN // DRIFT] Lagrangian Float Drift Velocity (cm/s)",
            xaxis_title="Surfacing Date",
            yaxis_title="Estimated Drift Speed (cm/s)",
            invert_y=False
        )

    df_clean = df_track.dropna(subset=[time_col, lat_col, lon_col]).copy()
    plat_col = col_map.get("PLATFORM_NUMBER")
    if plat_col and not df_clean.empty:
        if target_wmo is not None:
            df_clean = df_clean[df_clean[plat_col].astype(str) == str(target_wmo)]
        else:
            # Pick the float with the most distinct timestamps
            counts = df_clean.groupby(plat_col)[time_col].nunique()
            if not counts.empty:
                best_wmo = counts.idxmax()
                df_clean = df_clean[df_clean[plat_col] == best_wmo]

    df_t = df_clean.copy()
    df_t["TIME_DT"] = pd.to_datetime(df_t[time_col])

    cyc_col = col_map.get("CYCLE_NUMBER")
    if cyc_col:
        df_t = df_t.sort_values("TIME_DT").drop_duplicates(subset=[cyc_col])
    else:
        df_t = df_t.sort_values("TIME_DT").drop_duplicates(subset=["TIME_DT"])

    if len(df_t) < 2:
        fig.add_annotation(
            text="At least 2 surfacing timestamps are required to compute drift velocity.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=THEME_TEXT, size=14)
        )
        return _apply_siqva_theme(
            fig,
            title=title or "[DYN // DRIFT] Lagrangian Float Drift Velocity (cm/s)",
            xaxis_title="Surfacing Date",
            yaxis_title="Estimated Drift Speed (cm/s)",
            invert_y=False
        )

    lats = df_t[lat_col].values
    lons = df_t[lon_col].values
    times = df_t["TIME_DT"].values

    if gsw is not None:
        try:
            # Great-circle distance in meters via GSW
            dist_m = gsw.distance(lons, lats)
        except Exception:
            # Fallback haversine formula
            lat_rad = np.radians(lats)
            lon_rad = np.radians(lons)
            dlat = np.diff(lat_rad)
            dlon = np.diff(lon_rad)
            a = np.sin(dlat / 2.0)**2 + np.cos(lat_rad[:-1]) * np.cos(lat_rad[1:]) * np.sin(dlon / 2.0)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
            dist_m = 6371000.0 * c
    else:
        lat_rad = np.radians(lats)
        lon_rad = np.radians(lons)
        dlat = np.diff(lat_rad)
        dlon = np.diff(lon_rad)
        a = np.sin(dlat / 2.0)**2 + np.cos(lat_rad[:-1]) * np.cos(lat_rad[1:]) * np.sin(dlon / 2.0)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
        dist_m = 6371000.0 * c

    dt_sec = np.diff(times) / np.timedelta64(1, "s")
    valid = dt_sec > 0

    speed_cms = np.zeros_like(dist_m)
    speed_cms[valid] = (dist_m[valid] / dt_sec[valid]) * 100.0  # m/s to cm/s
    mid_times = times[1:]

    fig.add_trace(go.Scatter(
        x=mid_times,
        y=speed_cms,
        mode="lines+markers",
        line=dict(color="#00F0FF", width=2),
        marker=dict(
            size=7,
            color=speed_cms,
            colorscale="Plasma",
            showscale=True,
            colorbar=dict(title="cm/s")
        ),
        name="Drift Speed (cm/s)",
        hovertemplate="Date: %{x}<br>Drift Speed: %{y:.1f} cm/s<extra></extra>"
    ))

    # Threshold line for strong eddy / boundary current entrainment (~25 cm/s)
    fig.add_hline(
        y=25.0,
        line_dash="dot",
        line_color="#FF3366",
        annotation_text="High Current / Eddy Entrainment (>25 cm/s)",
        annotation_font_color="#FF3366"
    )

    return _apply_siqva_theme(
        fig,
        title=title or "[DYN // DRIFT] Lagrangian Float Drift Velocity (cm/s)",
        xaxis_title="Surfacing Date",
        yaxis_title="Estimated Drift Speed (cm/s)",
        invert_y=False
    )
