"""Plotly visualization templates for ArgoCard following the Deep Ocean dark theme."""

from __future__ import annotations

from typing import Any, Optional
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

