import streamlit as st
import streamlit.components.v1 as components

from src.bag.get_building_polygon import AddressOutOfCoverageError
from src.calc.damage_scanner_interface import (
    BuildingClassifierType,
    BuildingDataInput,
    DamageScannerInputs,
)
from src.ui.damage_scanner_visualiser import DamageVisualiser


st.set_page_config(page_title="Damage Scanner Prototype", layout="wide")


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


st.title("Damage Scanner Prototype")
st.write("Enter an address, run the scanner, and inspect the estimated damages on the map below.")

with st.form("damage_scanner_form"):
    address = st.text_input("Address", value="Science Park 608, 1098 XH Amsterdam, Netherlands")
    return_period = 100
    submitted = st.form_submit_button("Run scan")

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
                ead = visualiser.damage_scanner.get_damages()
                fmap = visualiser.build_map(ead)

            st.session_state["ead"] = ead
            st.session_state["map_html"] = _render_map_html(fmap)
            st.session_state["address"] = address
            st.session_state["return_period"] = return_period
        except AddressOutOfCoverageError as exc:
            _clear_results()
            st.error(str(exc))
        except Exception as exc:
            _clear_results()
            st.error(f"Damage scan failed: {exc}")

ead = st.session_state.get("ead")
map_html = st.session_state.get("map_html")

if ead is not None and map_html is not None:
    total_damage = float(ead["average_ead"].sum(skipna=True)) if "average_ead" in ead.columns else 0.0
    building_count = int(len(ead))
    max_damage = float(ead["average_ead"].max(skipna=True)) if "average_ead" in ead.columns else 0.0

    metric_cols = st.columns(3)
    metric_cols[0].metric("Buildings", building_count)
    metric_cols[1].metric("Total EAD", f"{total_damage:,.2f}")
    metric_cols[2].metric("Max EAD", f"{max_damage:,.2f}")

    st.subheader("Map")
    components.html(map_html, height=850, scrolling=True)

    st.subheader("Results")
    display_columns = [column for column in ead.columns if column != "geometry"]
    st.dataframe(ead[display_columns], use_container_width=True)
else:
    st.info("Run a scan to see the damage results and map.")