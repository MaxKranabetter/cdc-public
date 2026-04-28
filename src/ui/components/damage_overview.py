import streamlit as st
import pandas as pd

from src.ui.components.interactive_dropdown import interactive_dropdown
from src.ssm.models import DamageFunctionPackage, SSMFunctionMetadata, SSMFunctionType


def render_damage_metric_section(title: str,
                                 main_label: str,
                                 main_value: float,
                                 min_label: str,
                                 min_value: float,
                                 max_label: str,
                                 max_value: float):
    st.subheader(title)
    st.markdown(
        f"""
        <div style="display:flex; gap:0.9rem; align-items:stretch;">
            <div style="flex:2; min-height:8.5rem; padding:1rem 1.1rem; border:1px solid rgba(49, 51, 63, 0.15); border-radius:0.75rem; background:rgba(250, 250, 250, 0.6); display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:0.9rem; color:rgba(49, 51, 63, 0.7); margin-bottom:0.35rem;">{main_label}</div>
                <div style="font-size:2rem; font-weight:700; line-height:1.05;">{main_value:,.2f}</div>
            </div>
            <div style="flex:1; min-height:8.5rem; padding:1rem 1.1rem; border:1px solid rgba(49, 51, 63, 0.15); border-radius:0.75rem; background:rgba(250, 250, 250, 0.45); display:flex; flex-direction:column; justify-content:center; gap:0.55rem;">
                <div style="font-size:0.85rem; color:rgba(49, 51, 63, 0.7);">{min_label}</div>
                <div style="font-size:1.35rem; font-weight:600; line-height:1.05;">{min_value:,.2f}</div>
                <div style="font-size:0.85rem; color:rgba(49, 51, 63, 0.7);">{max_label}</div>
                <div style="font-size:1.35rem; font-weight:600; line-height:1.05;">{max_value:,.2f}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def build_damage_columns(damage_functions: dict[str, list[int]],
                         ead: pd.DataFrame,
                         function_metadata: dict[int, SSMFunctionMetadata],
                         focussed_function_name: str | None,
                         deselected_functions: list[str],
                         function_type_filter: list[SSMFunctionType] | None = None) -> tuple[float, float, float]:
    relevant_packages = [p for p in damage_functions.keys() if p not in deselected_functions]
    damages = []
    for name in relevant_packages:
        func_ids = damage_functions[name]
        current_damage = 0
        functions_considered = 0
        for func_id in func_ids:
            if function_type_filter is not None:
                metadata = function_metadata[func_id]
                if metadata.function_type not in function_type_filter:
                    continue
            functions_considered += 1
            if str(func_id) in ead.columns:
                current_damage += ead[str(func_id)].sum()
        if functions_considered > 0:
            damages.append(current_damage)

    min_damage = min(damages) if damages else 0
    max_damage = max(damages) if damages else 0

    if focussed_function_name:
        function_ids = damage_functions.get(focussed_function_name, [])
        if function_type_filter is not None:
            function_ids = [
                func_id for func_id in function_ids
                if function_metadata[func_id].function_type in function_type_filter
            ]
        focussed_damages = [ead[str(func_id)].sum() for func_id in function_ids if str(func_id) in ead.columns]
        total_damage = sum(focussed_damages)
    else:
        total_damage = sum(damages) / len(damages) if damages else 0

    return min_damage, total_damage, max_damage, len(damages)

def build_damage_overview_section(damage_functions: dict[str, list[int]],
                                  ead: pd.DataFrame,
                                  function_metadata: dict[int, SSMFunctionMetadata],
                                  all_packages: dict[str, DamageFunctionPackage]):
    focussed_function_name, deselected_functions = interactive_dropdown(
        label="Customise damage curves",
        items=[name for name in damage_functions.keys()],
    )
    
    min_total_damage, total_damage, max_total_damage, functions_considered = build_damage_columns(
        damage_functions,
        ead,
        function_metadata,
        focussed_function_name,
        deselected_functions
    )

    render_damage_metric_section(
        "Total Damage",
        "Estimated EAD" if focussed_function_name else "Average EAD",
        total_damage,
        "Min EAD",
        min_total_damage,
        "Max EAD",
        max_total_damage,
    )

    min_structural_damage, total_structural_damage, max_structural_damage, structural_functions_considered = build_damage_columns(
        damage_functions,
        ead,
        function_metadata,
        focussed_function_name,
        deselected_functions,
        function_type_filter=[SSMFunctionType.STRUCTURE]
    )

    print(f"Structural functions considered: {structural_functions_considered}")

    if structural_functions_considered > 0:
        render_damage_metric_section(
            "Of Which Structural Damage",
            "Estimated Structural EAD" if focussed_function_name else "Average Structural EAD",
            total_structural_damage,
            "Min Structural EAD",
            min_structural_damage,
            "Max Structural EAD",
            max_structural_damage,
        )

    min_content_damage, total_content_damage, max_content_damage, content_functions_considered = build_damage_columns(
        damage_functions,
        ead,
        function_metadata,
        focussed_function_name,
        deselected_functions,
        function_type_filter=[SSMFunctionType.CONTENT]
    )

    print(f"Content functions considered: {content_functions_considered}")

    if content_functions_considered > 0:
        render_damage_metric_section(
            "Of Which Content Damage",
            "Estimated Content EAD" if focussed_function_name else "Average Content EAD",
            total_content_damage,
            "Min Content EAD",
            min_content_damage,
            "Max Content EAD",
            max_content_damage,
        )

    min_inventory_damage, total_inventory_damage, max_inventory_damage, inventory_functions_considered = build_damage_columns(
        damage_functions,
        ead,
        function_metadata,
        focussed_function_name,
        deselected_functions,
        function_type_filter=[SSMFunctionType.INVENTORY]
    )

    print(f"Inventory functions considered: {inventory_functions_considered}")

    if inventory_functions_considered > 0:
        render_damage_metric_section(
            "Of Which Inventory Damage",
            "Estimated Inventory EAD" if focussed_function_name else "Average Inventory EAD",
            total_inventory_damage,
            "Min Inventory EAD",
            min_inventory_damage,
            "Max Inventory EAD",
            max_inventory_damage,
        )