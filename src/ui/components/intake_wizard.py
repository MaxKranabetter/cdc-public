from __future__ import annotations

import folium
import pandas as pd
import streamlit as st
import tempfile
from pathlib import Path

from calc.building_data_interface import BuildingDataInterface
from calc.models import BuildingClassifierType, BuildingDataInput
from src.ui.components.mock_intake_data import (
    MockBuildingContext,
    MockIntakeSelection,
    build_mock_building_context,
    build_mock_damage_preview,
    build_mock_result_payload,
    get_default_floor_height,
    get_specific_type_options,
    get_subtype_options,
)

STEP_ORDER = [
    "address",
    "confirm",
    "typology",
    "floor_height",
    "scope",
    "summary",
    "shared_damage",
    "complete",
]

STEP_LABELS = [
    "Address",
    "Confirm building",
    "Typology",
    "Floor height",
    "Scope",
    "Maximum damage",
    "Shared structure",
    "Preview ready",
]

USE_OPTIONS = ["Residential", "Employment", "Infrastructure"]
SCOPE_OPTIONS = ["Entire building", "Single unit only"]


def _clear_mock_results() -> None:
    for key in [
        "ead",
        "damage_functions",
        "all_packages",
        "function_metadata",
        "risk_profile_data",
        "map_html",
    ]:
        st.session_state.pop(key, None)


def _clear_preview_state() -> None:
    for key in ["intake_preview", "intake_result_payload"]:
        st.session_state.pop(key, None)


def _clear_typology_downstream() -> None:
    for key in [
        "intake_specific_type",
        "intake_floor_height_m",
        "intake_scope",
        "intake_total_floors",
        "intake_floor_areas_df",
        "intake_unit_area_m2",
        "intake_unit_floor",
        "intake_shared_damage_pct",
    ]:
        st.session_state.pop(key, None)
    _clear_preview_state()
    _clear_mock_results()


def _clear_specific_downstream() -> None:
    for key in [
        "intake_floor_height_m",
        "intake_scope",
        "intake_total_floors",
        "intake_floor_areas_df",
        "intake_unit_area_m2",
        "intake_unit_floor",
        "intake_shared_damage_pct",
    ]:
        st.session_state.pop(key, None)
    _clear_preview_state()
    _clear_mock_results()


def _clear_scope_downstream() -> None:
    st.session_state.pop("intake_shared_damage_pct", None)
    _clear_preview_state()
    _clear_mock_results()


def _collect_selection() -> MockIntakeSelection:
    floor_areas_df = st.session_state.get("intake_floor_areas_df")
    floor_areas: list[float] = []
    if isinstance(floor_areas_df, pd.DataFrame) and not floor_areas_df.empty and "area_m2" in floor_areas_df.columns:
        floor_areas = [float(value) for value in floor_areas_df["area_m2"].fillna(0).tolist()]

    return MockIntakeSelection(
        address=st.session_state.get("intake_address", ""),
        use=st.session_state.get("intake_use", USE_OPTIONS[0]),
        subtype=st.session_state.get("intake_subtype", get_subtype_options(USE_OPTIONS[0])[0]),
        specific_type=st.session_state.get("intake_specific_type"),
        floor_height_m=float(st.session_state.get("intake_floor_height_m", 2.75)),
        scope=st.session_state.get("intake_scope", SCOPE_OPTIONS[0]),
        total_floors=st.session_state.get("intake_total_floors"),
        floor_areas=floor_areas,
        unit_area_m2=st.session_state.get("intake_unit_area_m2"),
        unit_floor=st.session_state.get("intake_unit_floor"),
        shared_damage_pct=float(st.session_state.get("intake_shared_damage_pct", 35.0)),
    )


def _set_step(step: str) -> None:
    st.session_state["intake_step"] = step


def _go_to_step(step: str) -> None:
    st.session_state["intake_step"] = step
    st.rerun()


def _nav_button(label: str, *, step: str, next_step: str | None = None, key_suffix: str) -> bool:
    button_key = f"intake_nav_{key_suffix}_{step}"
    return st.button(label, key=button_key)


def _ensure_floor_areas(total_floors: int) -> pd.DataFrame:
    existing = st.session_state.get("intake_floor_areas_df")
    if isinstance(existing, pd.DataFrame) and len(existing) == total_floors:
        if list(existing.columns) == ["floor", "area_m2"]:
            return existing
    default_area = round(max(float(st.session_state.get("intake_unit_area_m2", 80.0)), 40.0), 2)
    return pd.DataFrame({"floor": list(range(1, total_floors + 1)), "area_m2": [default_area] * total_floors})


def _render_step_header(step_index: int) -> None:
    st.caption(f"Step {step_index + 1} of {len(STEP_LABELS)} · {STEP_LABELS[step_index]}")
    st.progress((step_index + 1) / len(STEP_LABELS))


def _render_address_step(building_interface: BuildingDataInterface) -> None:
    st.subheader("1. Address")
    st.write("Enter the address first. The rest of the flow uses mock data so the frontend can be tested immediately.")
    st.text_input("Building address", key="intake_address", placeholder="Radioweg 38, 1098 NJ Amsterdam, Netherlands")

    if st.button("Find building", type="primary", key="intake_find_building"):
        address = st.session_state.get("intake_address", "").strip()
        if not address:
            st.error("Please enter an address.")
            return
        _clear_mock_results()
        st.session_state["intake_building_context"] = building_interface.get_building_data(inputs=[
            BuildingDataInput(
                building_classifier_type=BuildingClassifierType.BAG,
                address=address
            )],
            as_fp=False
        )
        _go_to_step("confirm")


def _render_mock_map(building: MockBuildingContext) -> None:
    fmap = folium.Map(location=[building.centroid_lat, building.centroid_lon], zoom_start=19, tiles="CartoDB positron")
    folium.GeoJson(
        building.polygon.__geo_interface__,
        name="Selected building",
        style_function=lambda _: {
            "fillColor": "#5b8def",
            "color": "#21467b",
            "weight": 2,
            "fillOpacity": 0.45,
        },
    ).add_to(fmap)
    folium.Marker(
        [building.centroid_lat, building.centroid_lon],
        tooltip=building.building_label,
    ).add_to(fmap)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as temp_file:
        temp_file.write(fmap.get_root().render())
        temp_path = Path(temp_file.name)
    st.iframe(str(temp_path), height=420)


def _render_confirm_step() -> None:
    st.subheader("2. Confirm building")
    building = st.session_state.get("intake_building_context")
    if not isinstance(building, MockBuildingContext):
        st.warning("No building context available yet. Please go back and enter an address again.")
        if st.button("Back to address", key="intake_back_to_address"):
            _go_to_step("address")
        return

    cols = st.columns([1.25, 1, 1])
    with cols[0]:
        st.markdown(f"**Selected building**  \n{building.building_label}")
        st.write(f"Address: {building.address}")
        st.write(f"Neighborhood: {building.neighborhood}")
        st.write(f"Building ID: {building.building_id}")
    with cols[1]:
        st.metric("Centroid latitude", f"{building.centroid_lat:.5f}")
        st.metric("Centroid longitude", f"{building.centroid_lon:.5f}")
    with cols[2]:
        st.metric("Polygon vertices", len(list(building.polygon.exterior.coords)) - 1)

    _render_mock_map(building)

    nav = st.columns([1, 1, 4])
    with nav[0]:
        if _nav_button("Back", step="confirm", key_suffix="back"):
            _go_to_step("address")
    with nav[1]:
        if _nav_button("Confirm building", step="confirm", key_suffix="confirm"):
            _go_to_step("typology")


def _render_typology_step() -> None:
    st.subheader("3. Use and subtype")

    if "intake_use" not in st.session_state:
        st.session_state["intake_use"] = USE_OPTIONS[0]
    use = st.selectbox("Use", USE_OPTIONS, key="intake_use", on_change=_clear_typology_downstream)

    subtype_options = get_subtype_options(use)
    subtype_default = st.session_state.get("intake_subtype")
    if subtype_default not in subtype_options:
        st.session_state["intake_subtype"] = subtype_options[0]
    subtype = st.selectbox("Subtype", subtype_options, key="intake_subtype", on_change=_clear_typology_downstream)

    specific_options = get_specific_type_options(use, subtype)
    if specific_options:
        specific_default = st.session_state.get("intake_specific_type")
        if specific_default not in specific_options:
            st.session_state["intake_specific_type"] = specific_options[0]
        st.selectbox("Specific type", specific_options, key="intake_specific_type", on_change=_clear_specific_downstream)
    else:
        st.session_state.pop("intake_specific_type", None)
        st.info("No level 3 categories apply for this subtype.")

    nav = st.columns([1, 1, 4])
    with nav[0]:
        if _nav_button("Back", step="typology", key_suffix="back"):
            _go_to_step("confirm")
    with nav[1]:
        if _nav_button("Continue", step="typology", key_suffix="continue"):
            if not st.session_state.get("intake_subtype"):
                st.error("Please choose a subtype.")
                return
            _go_to_step("floor_height")


def _render_floor_height_step() -> None:
    st.subheader("4. Floor height")
    use = st.session_state.get("intake_use", USE_OPTIONS[0])
    subtype = st.session_state.get("intake_subtype", get_subtype_options(use)[0])
    specific_type = st.session_state.get("intake_specific_type")
    default_floor_height = get_default_floor_height(use, subtype, specific_type)

    st.caption("The default value comes from the selected typology and can be changed here.")
    st.number_input(
        "Floor height (m)",
        min_value=1.5,
        max_value=8.0,
        value=float(st.session_state.get("intake_floor_height_m", default_floor_height)),
        step=0.05,
        format="%.2f",
        key="intake_floor_height_m",
    )

    nav = st.columns([1, 1, 4])
    with nav[0]:
        if _nav_button("Back", step="floor_height", key_suffix="back"):
            _go_to_step("typology")
    with nav[1]:
        if _nav_button("Continue", step="floor_height", key_suffix="continue"):
            _go_to_step("scope")


def _render_scope_step() -> None:
    st.subheader("5. Damage scope")
    st.radio("Calculate damages for", SCOPE_OPTIONS, key="intake_scope", horizontal=True, on_change=_clear_scope_downstream)

    scope = st.session_state.get("intake_scope", SCOPE_OPTIONS[0])
    if scope == "Single unit only":
        st.number_input("Unit area (m²)", min_value=1.0, max_value=5000.0, value=float(st.session_state.get("intake_unit_area_m2", 65.0)), step=1.0, key="intake_unit_area_m2")
        st.number_input("Unit floor", min_value=0, max_value=100, value=int(st.session_state.get("intake_unit_floor", 1)), step=1, key="intake_unit_floor")
        st.info("Mock mode: the selected unit is treated as a single repeating footprint for preview purposes.")
    else:
        total_floors = int(st.number_input("Total floors", min_value=1, max_value=100, value=int(st.session_state.get("intake_total_floors", 3)), step=1, key="intake_total_floors"))
        floor_table = _ensure_floor_areas(total_floors)
        edited_table = st.data_editor(
            floor_table,
            num_rows="fixed",
            hide_index=True,
            width="stretch",
            column_config={
                "floor": st.column_config.NumberColumn("Floor", disabled=True, format="%d"),
                "area_m2": st.column_config.NumberColumn("Area per floor (m²)", min_value=0.0, step=1.0, format="%.2f"),
            },
            key="intake_floor_areas_editor",
        )
        if isinstance(edited_table, pd.DataFrame):
            st.session_state["intake_floor_areas_df"] = edited_table
        total_area = 0.0
        if isinstance(st.session_state.get("intake_floor_areas_df"), pd.DataFrame):
            total_area = float(st.session_state["intake_floor_areas_df"]["area_m2"].sum())
        st.caption(f"Total area: {total_area:.2f} m²")

    nav = st.columns([1, 1, 4])
    with nav[0]:
        if _nav_button("Back", step="scope", key_suffix="back"):
            _go_to_step("floor_height")
    with nav[1]:
        if _nav_button("Continue", step="scope", key_suffix="continue"):
            if scope == "Entire building":
                floor_areas_df = st.session_state.get("intake_floor_areas_df")
                if not isinstance(floor_areas_df, pd.DataFrame) or floor_areas_df.empty:
                    st.error("Please provide floor areas for the building.")
                    return
            else:
                if float(st.session_state.get("intake_unit_area_m2", 0.0)) <= 0:
                    st.error("Please enter a unit area.")
                    return
            _go_to_step("summary")


def _render_summary_step() -> None:
    st.subheader("6. Maximum damage preview")
    preview = build_mock_damage_preview(_collect_selection())
    st.session_state["intake_preview"] = preview

    columns = st.columns(3)
    columns[0].metric("Structural damage", f"€ {preview.structural_max:,.2f}")
    columns[1].metric("Content damage", f"€ {preview.content_max:,.2f}")
    if preview.inventory_enabled and preview.inventory_max is not None:
        columns[2].metric("Inventory damage", f"€ {preview.inventory_max:,.2f}")
    else:
        columns[2].metric("Inventory damage", "Not applicable")

    st.caption(f"Preview area used for the calculation: {preview.total_area_m2:,.2f} m²")
    st.caption("These are mock values meant to support the frontend while the real data pipeline is built.")

    nav = st.columns([1, 1, 4])
    with nav[0]:
        if _nav_button("Back", step="summary", key_suffix="back"):
            _go_to_step("scope")
    with nav[1]:
        if _nav_button("Continue", step="summary", key_suffix="continue"):
            _go_to_step("shared_damage")


def _render_shared_damage_step() -> None:
    st.subheader("7. Shared structural damage")
    preview = st.session_state.get("intake_preview")
    if not preview:
        preview = build_mock_damage_preview(_collect_selection())
        st.session_state["intake_preview"] = preview

    st.write("Confirm how much of the structural damage should be treated as shared infrastructure across all floors or units.")
    st.number_input(
        "Shared structural damage (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(st.session_state.get("intake_shared_damage_pct", 35.0)),
        step=1.0,
        key="intake_shared_damage_pct",
    )

    nav = st.columns([1, 1, 4])
    with nav[0]:
        if _nav_button("Back", step="shared_damage", key_suffix="back"):
            _go_to_step("summary")
    with nav[1]:
        if st.button("Generate preview", type="primary", key="intake_generate_preview"):
            selection = _collect_selection()
            building = st.session_state.get("intake_building_context")
            if not isinstance(building, MockBuildingContext):
                st.error("No building context is available.")
                return
            result_payload = build_mock_result_payload(selection, building)
            st.session_state["ead"] = result_payload.ead
            st.session_state["damage_functions"] = result_payload.damage_functions
            st.session_state["all_packages"] = result_payload.all_packages
            st.session_state["function_metadata"] = result_payload.function_metadata
            st.session_state["risk_profile_data"] = result_payload.risk_profile_data
            st.session_state["address"] = selection.address
            st.session_state["return_period"] = 100
            st.session_state["intake_result_payload"] = result_payload
            _go_to_step("complete")


def _render_complete_step() -> None:
    st.subheader("8. Preview ready")
    st.success("The mock frontend flow is complete and the result panels below are now populated with synthetic data.")
    preview = st.session_state.get("intake_preview")
    if preview:
        summary_columns = st.columns(4)
        summary_columns[0].metric("Total area", f"{preview.total_area_m2:,.2f} m²")
        summary_columns[1].metric("Structural", f"€ {preview.structural_max:,.2f}")
        summary_columns[2].metric("Content", f"€ {preview.content_max:,.2f}")
        summary_columns[3].metric("Shared structural", f"€ {preview.shared_structural_damage:,.2f}")

    nav = st.columns([1, 4])
    with nav[0]:
        if st.button("Start over", key="intake_start_over"):
            for key in [
                "intake_step",
                "intake_address",
                "intake_building_context",
                "intake_use",
                "intake_subtype",
                "intake_specific_type",
                "intake_floor_height_m",
                "intake_scope",
                "intake_total_floors",
                "intake_floor_areas_df",
                "intake_unit_area_m2",
                "intake_unit_floor",
                "intake_shared_damage_pct",
                "intake_preview",
                "intake_result_payload",
            ]:
                st.session_state.pop(key, None)
            _clear_mock_results()
            _go_to_step("address")


def render_intake_wizard() -> None:
    st.session_state.setdefault("intake_step", "address")
    st.session_state.setdefault("intake_use", USE_OPTIONS[0])
    st.session_state.setdefault("intake_subtype", get_subtype_options(USE_OPTIONS[0])[0])
    st.session_state.setdefault("intake_shared_damage_pct", 35.0)

    step = st.session_state["intake_step"]
    if step not in STEP_ORDER:
        step = "address"
        st.session_state["intake_step"] = step
    step_index = STEP_ORDER.index(step)

    with st.container(border=True):
        _render_step_header(step_index)
        if step == "address":
            _render_address_step()
        elif step == "confirm":
            _render_confirm_step()
        elif step == "typology":
            _render_typology_step()
        elif step == "floor_height":
            _render_floor_height_step()
        elif step == "scope":
            _render_scope_step()
        elif step == "summary":
            _render_summary_step()
        elif step == "shared_damage":
            _render_shared_damage_step()
        else:
            _render_complete_step()
