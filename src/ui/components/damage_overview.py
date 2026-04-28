import streamlit as st
import pandas as pd

from src.ui.components.interactive_dropdown import interactive_dropdown


def build_damage_overview_section(damage_functions: dict[str, list[int]], ead: pd.DataFrame):
    focussed_function, deselected_functions = interactive_dropdown(
        label="Customise damage curves",
        items=[name for name in damage_functions.keys()],
    )

    # all_function_ids = [curve_id for package in selected_curves for curve_id in package.ids]

    focussed_function_name = next((name for name in damage_functions.keys() if name == focussed_function)) if focussed_function else None
    
    relevant_packages = [p for p in damage_functions.keys() if p not in deselected_functions]
    damages = []
    for name in relevant_packages:
        func_ids = damage_functions[name]
        current_damage = 0
        for func_id in func_ids:
            if str(func_id) in ead.columns:
                current_damage += ead[str(func_id)].sum()
        damages.append(current_damage)

    min_damage = min(damages) if damages else 0
    max_damage = max(damages) if damages else 0

    if focussed_function_name:
        function_ids = damage_functions.get(focussed_function_name, [])
        focussed_damages = [ead[str(func_id)].sum() for func_id in function_ids if str(func_id) in ead.columns]
        total_damage = sum(focussed_damages)
    else:
        total_damage = sum(damages) / len(damages) if damages else 0

    metric_cols = st.columns(3)
    metric_cols[0].metric("Min EAD", f"{min_damage:,.2f}")
    metric_cols[1].metric("Estimated EAD" if focussed_function else "Average EAD", f"{total_damage:,.2f}")
    metric_cols[2].metric("Max EAD", f"{max_damage:,.2f}")