import streamlit as st
import pandas as pd

from src.ui.components.interactive_dropdown import interactive_dropdown
from src.ssm.models import DamageFunctionPackage, SSMFunctionMetadata, SSMFunctionType

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

    st.subheader("Total Damage")
    metric_cols = st.columns(3)
    metric_cols[0].metric("Min EAD", f"{min_total_damage:,.2f}")
    metric_cols[1].metric("Estimated EAD" if focussed_function_name else "Average EAD", f"{total_damage:,.2f}")
    metric_cols[2].metric("Max EAD", f"{max_total_damage:,.2f}")

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
        st.subheader("Of Which Structural Damage")
        metric_cols = st.columns(3)
        metric_cols[0].metric("Min Structural EAD", f"{min_structural_damage:,.2f}")
        metric_cols[1].metric("Estimated Structural EAD" if focussed_function_name else "Average Structural EAD", f"{total_structural_damage:,.2f}")
        metric_cols[2].metric("Max Structural EAD", f"{max_structural_damage:,.2f}")

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
        st.subheader("Of Which Content Damage")
        metric_cols = st.columns(3)
        metric_cols[0].metric("Min Content EAD", f"{min_content_damage:,.2f}")
        metric_cols[1].metric("Estimated Content EAD" if focussed_function_name else "Average Content EAD", f"{total_content_damage:,.2f}")
        metric_cols[2].metric("Max Content EAD", f"{max_content_damage:,.2f}")

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
        st.subheader("Of Which Inventory Damage")
        metric_cols = st.columns(3)
        metric_cols[0].metric("Min Inventory EAD", f"{min_inventory_damage:,.2f}")
        metric_cols[1].metric("Estimated Inventory EAD" if focussed_function_name else "Average Inventory EAD", f"{total_inventory_damage:,.2f}")
        metric_cols[2].metric("Max Inventory EAD", f"{max_inventory_damage:,.2f}")