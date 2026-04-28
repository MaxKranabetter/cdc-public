import streamlit as st

from src.bag.get_building_polygon import AddressOutOfCoverageError
from src.ui.damage_scanner_visualiser import DamageVisualiser
from src.ssm.models import DamageFunctionPackage

from src.calc.models import (
    BuildingClassifierType,
    BuildingDataInput,
    DamageScannerInputs,
)

def _build_inputs(address: str) -> DamageScannerInputs:
    return DamageScannerInputs(
        building_inputs=[
            BuildingDataInput(
                address=address,
                building_classifier_type=BuildingClassifierType.BAG,
            )
        ]
    )

def location_input_form():
    with st.form("damage_scanner_form"):
        address = st.text_input("Address", value="Science Park 608, 1098 XH Amsterdam, Netherlands")
        return_period = 100
        submitted = st.form_submit_button("Run calculation")

    if submitted:
        if not address.strip():
            st.error("Please enter an address.")
        else:
            def _clear_results() -> None:
                st.session_state.pop("ead", None)
                st.session_state.pop("map_html", None)

            try:
                with st.spinner("Loading buildings and calculating damages..."):
                    visualiser = DamageVisualiser(_build_inputs(address), selected_return_period=return_period)
                    ds = visualiser.damage_scanner
                    ead = ds.get_damages()
                    fmap = visualiser.build_map(ead)

                st.session_state["ead"] = ead
                st.session_state["map_html"] = fmap.get_root().render()
                st.session_state["address"] = address
                st.session_state["return_period"] = return_period
                selected_curves: list[DamageFunctionPackage] = ds.damage_function_package_mapping.values()
                st.session_state["damage_functions"] = {fp.metadata.name: fp.ids for fp in selected_curves}
                st.session_state["all_packages"] = {fp.metadata.name: fp for fp in ds.damage_function_package_mapping.values()}
                st.session_state["function_metadata"] = ds.damage_function_interface.damage_function_metadata
            except AddressOutOfCoverageError as exc:
                _clear_results()
                st.error(str(exc))
            except Exception as exc:
                _clear_results()
                st.error(f"Damage scan failed: {exc}")