import streamlit as st
import streamlit.components.v1 as components

from src.bag.get_building_polygon import AddressOutOfCoverageError
from src.calc.models import (
    BuildingClassifierType,
    BuildingDataInput,
    DamageScannerInputs,
)
from src.ui.damage_scanner_visualiser import DamageVisualiser
from src.ui.components.interactive_dropdown import interactive_dropdown


st.set_page_config(page_title="CDC Prototype", layout="wide")


def _build_inputs(address: str) -> DamageScannerInputs:
    return DamageScannerInputs(
        building_inputs=[
            BuildingDataInput(
                address=address,
                building_classifier_type=BuildingClassifierType.BAG,
            )
        ]
    )


def _render_map_html(fmap) -> str:
    return fmap.get_root().render()


st.title("CDC Prototype")
st.write("Enter an address, run the tool, and inspect the estimated damages on the map below.")

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
            st.session_state["map_html"] = _render_map_html(fmap)
            st.session_state["address"] = address
            st.session_state["return_period"] = return_period
            selected_curve_ids = ds.damage_functions.columns[1:].tolist() # columns are damage function names
            functions = [ds.damage_function_interface.damage_functions.get(curve_id) for curve_id in selected_curve_ids if curve_id.isdigit()]
            st.session_state["damage_functions"] = [(selected_curve_ids[i], f.metadata.name) for i, f in enumerate(functions) if f]
        except AddressOutOfCoverageError as exc:
            _clear_results()
            st.error(str(exc))
        except Exception as exc:
            _clear_results()
            st.error(f"Damage scan failed: {exc}")

ead = st.session_state.get("ead")
map_html = st.session_state.get("map_html")

if ead is not None and map_html is not None:
    st.subheader("Map")
    components.html(map_html, height=850, scrolling=True)

    st.subheader("Damage Curves")
    focussed_function, deselected_functions = interactive_dropdown(
        label="Customise damage curves",
        items=[name for id, name in st.session_state.get("damage_functions", [])]
    )

    focussed_function_id = next((id for id, name in st.session_state.get("damage_functions", []) if name == focussed_function)) if focussed_function else "average_ead"
    selected_function_ids = [id for id, name in st.session_state.get("damage_functions", []) if name not in deselected_functions]
    damages = [ead[col].sum() for col in ead.columns if col in selected_function_ids]

    min_damage = min(damages) if damages else 0
    max_damage = max(damages) if damages else 0
    total_damage = ead[focussed_function_id].sum()

    metric_cols = st.columns(3)
    metric_cols[0].metric("Min EAD", f"{min_damage:,.2f}")
    metric_cols[1].metric("Estimated EAD" if focussed_function else "Average EAD", f"{total_damage:,.2f}")
    metric_cols[2].metric("Max EAD", f"{max_damage:,.2f}")
else:
    pass
    #st.info("Run a scan to see the damage results and map.")