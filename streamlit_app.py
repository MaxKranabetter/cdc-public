import streamlit as st
from src.calc.floodmap_interface import FloodmapInterface
from src.ui.components.damage_overview import build_damage_overview_section
from src.ui.components.location_input_form import location_input_form
from src.ui.components.risk_profile_overview import build_risk_profile_overview_section

st.set_page_config(page_title="CDC Prototype", layout="wide")

st.title("CDC Prototype")
st.write("Use the wizard below to test the intake flow. It currently runs on mock frontend data.")
floodmap_interface = FloodmapInterface()
location_input_form(floodmap_interface.get_representative_floodmap_path())

ead = st.session_state.get("ead")
all_packages = st.session_state.get("all_packages", {})
function_metadata = st.session_state.get("function_metadata", {})
map_html = st.session_state.get("map_html")

if ead is not None:# and map_html is not None:
    #st.subheader("Map")
    #st.iframe(map_html, height=850)

    damage_functions: dict[str, list[int]] = st.session_state.get("damage_functions", {})

    st.subheader("Damage Overview")
    build_damage_overview_section(damage_functions, ead, function_metadata, all_packages)

    build_risk_profile_overview_section(st.session_state["risk_profile_data"])
else:
    pass
    #st.info("Run a scan to see the damage results and map.")