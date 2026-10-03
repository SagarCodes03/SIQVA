# src/visualizer.py
import plotly.graph_objects as go
import pandas as pd

def plot_depth_profile(df: pd.DataFrame, wmo_id: int, variable: str = 'TEMP'):
    """Generates an interactive profile chart dynamically based on the requested variable."""
    if df.empty or variable not in df.columns:
        return None

    # Map the database variable to readable labels
    var_labels = {
        'TEMP': 'Temperature (°C)',
        'PSAL': 'Salinity (PSU)'
    }
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
            marker=dict(size=4)
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