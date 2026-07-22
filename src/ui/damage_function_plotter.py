from __future__ import annotations

import plotly.graph_objects as go

from src.ssm.ssm_function_loader import get_function_from_id


def plot_damage_functions(damage_function_ids: list[int]) -> go.Figure:
    """Plot one or more damage functions on a single chart.

    Each curve is loaded by id and drawn as a depth-to-damage-factor line.
    """
    figure = go.Figure()

    for damage_function_id in damage_function_ids:
        damage_function = get_function_from_id(damage_function_id)
        if damage_function is None:
            continue

        depths = sorted(damage_function.values.keys())
        factors = [damage_function.values[depth] for depth in depths]
        metadata = damage_function.metadata
        label = f"{metadata.id}: {metadata.name}"

        figure.add_trace(
            go.Scatter(
                x=depths,
                y=factors,
                mode="lines+markers",
                name=label,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Depth: %{x:.3f} m<br>"
                    "Damage factor: %{y:.3f}<extra></extra>"
                ),
            )
        )

    if not figure.data:
        raise ValueError("No valid damage functions were found for the provided ids.")

    figure.update_layout(
        title="Damage functions",
        xaxis_title="Flood depth (m)",
        yaxis_title="Damage factor",
        template="plotly_white",
        legend_title_text="Damage function",
    )
    figure.update_xaxes(rangemode="tozero")
    figure.update_yaxes(rangemode="tozero")
    
    figure.show()