# src/visualizer.py
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

def plot_depth_profile(df: pd.DataFrame, wmo_id: int, variable: str = 'TEMP'):
    """Generates an interactive profile chart dynamically based on the requested variable."""
    if df.empty or variable not in df.columns:
        return None

    # Format dates to be more readable
    df['TIME'] = pd.to_datetime(df['TIME']).dt.strftime('%Y-%m-%d')

    var_labels = {'TEMP': 'Temperature (°C)', 'PSAL': 'Salinity (PSU)'}
    x_label = var_labels.get(variable, variable)

    cycles = sorted(df['CYCLE_NUMBER'].unique())
    latest_cycle = cycles[-1]

    fig = go.Figure()

    for cycle in cycles:
        cycle_data = df[df['CYCLE_NUMBER'] == cycle]
        visibility_state = True if cycle == latest_cycle else 'legendonly'

        fig.add_trace(go.Scatter(
            x=cycle_data[variable],
            y=cycle_data['PRES'],
            mode='lines+markers',
            name=f'Cycle {cycle}',
            visible=visibility_state,
            marker=dict(size=4),
            customdata=cycle_data[['TIME', 'LATITUDE', 'LONGITUDE']],
            hovertemplate=(
                f"<b>{x_label.split(' ')[0]}:</b> %{{x}}<br>"
                "<b>Depth:</b> %{y} dbar<br>"
                "<b>Date:</b> %{customdata[0]}<br>"
                "<b>Lat/Lon:</b> %{customdata[1]:.2f}°, %{customdata[2]:.2f}°<br>"
                "<extra></extra>"
            )
        ))

    fig.update_layout(
        title=f"ARGO Float {wmo_id} - {x_label} vs Depth",
        xaxis_title=x_label,
        yaxis_title="Pressure / Depth (dbar)",
        yaxis=dict(autorange="reversed"),
        template="plotly_dark",
        height=600,
        legend_title_text="Cycles (Click to toggle)"
    )

    return fig

def plot_position_map(floats_data: list, location_name: str):
    """Generates an interactive map showing ARGO float locations."""
    if not floats_data:
        return None
        
    df = pd.DataFrame(floats_data)
    
    # Updated for newer Plotly versions: scatter_map replaces scatter_mapbox
    fig = px.scatter_map(
        df, 
        lat="latitude", 
        lon="longitude", 
        hover_name="float_wmo",
        hover_data={"latitude": ":.2f", "longitude": ":.2f", "profile_date": True},
        color_discrete_sequence=["#48cae4"],
        zoom=2, # slightly zoomed out for the global view
        title=f"Active ARGO Floats: {location_name}"
    )
    
    # Updated: map_style replaces mapbox_style
    fig.update_layout(
        map_style="carto-darkmatter",
        margin={"r":0,"t":40,"l":0,"b":0},
        template="plotly_dark",
        paper_bgcolor="#0b132a",
        height=500
    )
    
    return fig