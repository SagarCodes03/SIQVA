"""Plotly visualization templates for ArgoCard following the Deep Ocean dark theme."""

from __future__ import annotations

from typing import Any, Optional
import gsw
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

    if pres_col:
        marker_dict = dict(
            size=4,
            color=valid_df[pres_col],
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
        go.Scatter(
            x=valid_df["PSAL"],
            y=valid_df["TEMP"],
            mode="markers",
            marker=marker_dict,
            hovertemplate="Salinity: %{x:.2f}<br>Temp: %{y:.2f} °C<extra></extra>",
        )
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
        sub["depth_m"] = -gsw.z_from_p(p_arr, lat_val)

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

