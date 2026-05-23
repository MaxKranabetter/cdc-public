from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from shapely.geometry import Polygon

from src.ssm.models import (
    Country,
    DamageLevel,
    DamageModel,
    DamageFunctionPackage,
    IntensityUnit,
    L1FunctionCategory,
    L2FunctionCategory,
    L3FunctionCategory,
    SSMFunction,
    SSMFunctionMethod,
    SSMFunctionMetadata,
    SSMFunctionScale,
    SSMFunctionType,
)

TYPOLOGY_FLOW: dict[str, dict[str, list[str]]] = {
    "Residential": {
        "Apartments": [],
        "Single Family": ["Terraced", "Semi detached", "Fully detached"],
    },
    "Employment": {
        "Agriculture": [],
        "Commercial": ["Bank", "HoReCa", "Sports & Recreation"],
        "Education": ["Library", "School"],
        "Hospital": [],
        "Industrial": ["Warehouse"],
        "Office": ["Social Infrastructure"],
    },
    "Infrastructure": {
        "Transportation": [],
        "Water": [],
    },
}

DEFAULT_FLOOR_HEIGHTS: dict[tuple[str, str, str | None], float] = {
    ("Residential", "Apartments", None): 2.75,
    ("Residential", "Single Family", "Terraced"): 2.6,
    ("Residential", "Single Family", "Semi detached"): 2.7,
    ("Residential", "Single Family", "Fully detached"): 2.8,
    ("Employment", "Agriculture", None): 3.0,
    ("Employment", "Commercial", "Bank"): 3.2,
    ("Employment", "Commercial", "HoReCa"): 3.4,
    ("Employment", "Commercial", "Sports & Recreation"): 4.0,
    ("Employment", "Education", "Library"): 3.1,
    ("Employment", "Education", "School"): 3.3,
    ("Employment", "Hospital", None): 3.4,
    ("Employment", "Industrial", "Warehouse"): 4.5,
    ("Employment", "Office", "Social Infrastructure"): 3.1,
    ("Infrastructure", "Transportation", None): 5.0,
    ("Infrastructure", "Water", None): 3.0,
}

USE_CATEGORY_MAP: dict[str, L1FunctionCategory] = {
    "Residential": L1FunctionCategory.RESIDENTIAL,
    "Employment": L1FunctionCategory.EMPLOYMENT,
    "Infrastructure": L1FunctionCategory.INFRASTRUCTURE,
}

SUBTYPE_CATEGORY_MAP: dict[tuple[str, str], L2FunctionCategory] = {
    ("Residential", "Apartments"): L2FunctionCategory.APARTMENTS,
    ("Residential", "Single Family"): L2FunctionCategory.SINGLE_FAMILY,
    ("Employment", "Agriculture"): L2FunctionCategory.AGRICULTURE,
    ("Employment", "Commercial"): L2FunctionCategory.COMMERCIAL,
    ("Employment", "Education"): L2FunctionCategory.EDUCATION,
    ("Employment", "Hospital"): L2FunctionCategory.HOSPITAL,
    ("Employment", "Industrial"): L2FunctionCategory.INDUSTRIAL,
    ("Employment", "Office"): L2FunctionCategory.OFFICE,
    ("Infrastructure", "Transportation"): L2FunctionCategory.TRANSPORTATION,
    ("Infrastructure", "Water"): L2FunctionCategory.WATER,
}

SPECIFIC_CATEGORY_MAP: dict[tuple[str, str, str], L3FunctionCategory] = {
    ("Residential", "Single Family", "Terraced"): L3FunctionCategory.TERRACED,
    ("Residential", "Single Family", "Semi detached"): L3FunctionCategory.SEMI_DETACHED,
    ("Residential", "Single Family", "Fully detached"): L3FunctionCategory.FULLY_DETACHED,
    ("Employment", "Commercial", "Bank"): L3FunctionCategory.BANK,
    ("Employment", "Commercial", "HoReCa"): L3FunctionCategory.HORECA,
    ("Employment", "Commercial", "Sports & Recreation"): L3FunctionCategory.SPORTS_AND_RECREATION,
    ("Employment", "Education", "Library"): L3FunctionCategory.LIBRARY,
    ("Employment", "Education", "School"): L3FunctionCategory.SCHOOL,
    ("Employment", "Industrial", "Warehouse"): L3FunctionCategory.WAREHOUSE,
    ("Employment", "Office", "Social Infrastructure"): L3FunctionCategory.SOCIAL_INFRASTRUCTURE,
}

USE_FACTOR_MAP = {
    "Residential": 1.0,
    "Employment": 1.25,
    "Infrastructure": 1.4,
}

SUBTYPE_FACTOR_MAP = {
    "Apartments": 0.85,
    "Single Family": 0.95,
    "Agriculture": 0.7,
    "Commercial": 1.1,
    "Education": 1.0,
    "Hospital": 1.15,
    "Industrial": 1.2,
    "Office": 1.0,
    "Transportation": 1.05,
    "Water": 0.9,
}

SPECIFIC_FACTOR_MAP = {
    "Terraced": 0.92,
    "Semi detached": 0.97,
    "Fully detached": 1.05,
    "Bank": 1.08,
    "HoReCa": 1.12,
    "Sports & Recreation": 1.02,
    "Library": 0.96,
    "School": 1.0,
    "Warehouse": 1.1,
    "Social Infrastructure": 1.03,
}


@dataclass(frozen=True)
class MockBuildingContext:
    address: str
    building_label: str
    building_id: str
    neighborhood: str
    centroid_lat: float
    centroid_lon: float
    polygon: Polygon


@dataclass(frozen=True)
class MockIntakeSelection:
    address: str
    use: str
    subtype: str
    specific_type: str | None
    floor_height_m: float
    scope: str
    total_floors: int | None
    floor_areas: list[float]
    unit_area_m2: float | None
    unit_floor: int | None
    shared_damage_pct: float


@dataclass(frozen=True)
class MockDamagePreview:
    total_area_m2: float
    structural_max: float
    content_max: float
    inventory_max: float | None
    inventory_enabled: bool
    shared_structural_damage: float


@dataclass(frozen=True)
class MockResultPayload:
    ead: pd.DataFrame
    damage_functions: dict[str, list[int]]
    all_packages: dict[str, DamageFunctionPackage]
    function_metadata: dict[int, SSMFunctionMetadata]
    risk_profile_data: dict[str, list[tuple[int, float]]]


def get_subtype_options(use: str) -> list[str]:
    return list(TYPOLOGY_FLOW.get(use, {}).keys())


def get_specific_type_options(use: str, subtype: str) -> list[str]:
    return list(TYPOLOGY_FLOW.get(use, {}).get(subtype, []))


def get_default_floor_height(use: str, subtype: str, specific_type: str | None = None) -> float:
    lookup_key = (use, subtype, specific_type)
    if lookup_key in DEFAULT_FLOOR_HEIGHTS:
        return DEFAULT_FLOOR_HEIGHTS[lookup_key]
    fallback_key = (use, subtype, None)
    if fallback_key in DEFAULT_FLOOR_HEIGHTS:
        return DEFAULT_FLOOR_HEIGHTS[fallback_key]
    return 3.0


def resolve_typology_categories(use: str, subtype: str, specific_type: str | None) -> tuple[L1FunctionCategory, L2FunctionCategory, list[L3FunctionCategory]]:
    l1_category = USE_CATEGORY_MAP[use]
    l2_category = SUBTYPE_CATEGORY_MAP[(use, subtype)]
    if specific_type is None:
        return l1_category, l2_category, []
    specific_category = SPECIFIC_CATEGORY_MAP[(use, subtype, specific_type)]
    return l1_category, l2_category, [specific_category]


def _deterministic_offset(seed_value: int, scale: float, shift: float = 0.0) -> float:
    return shift + ((seed_value % 100) / 100.0 - 0.5) * scale


def build_mock_building_context(address: str) -> MockBuildingContext:
    seed_value = sum(ord(character) for character in address)
    centroid_lat = 52.3676 + _deterministic_offset(seed_value, 0.012)
    centroid_lon = 4.9041 + _deterministic_offset(seed_value // 2, 0.014)
    width = 0.00045 + (seed_value % 5) * 0.00003
    height = 0.00035 + (seed_value % 7) * 0.00002
    polygon = Polygon(
        [
            (centroid_lon - width, centroid_lat - height),
            (centroid_lon + width, centroid_lat - height),
            (centroid_lon + width, centroid_lat + height),
            (centroid_lon - width, centroid_lat + height),
        ]
    )
    return MockBuildingContext(
        address=address,
        building_label=f"Mock building near {address.split(',')[0].strip() or 'selected address'}",
        building_id=f"mock-{abs(seed_value) % 10000:04d}",
        neighborhood="Amsterdam Centrum",
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        polygon=polygon,
    )


def _typology_factor(use: str, subtype: str, specific_type: str | None) -> float:
    factor = USE_FACTOR_MAP.get(use, 1.0) * SUBTYPE_FACTOR_MAP.get(subtype, 1.0)
    if specific_type is not None:
        factor *= SPECIFIC_FACTOR_MAP.get(specific_type, 1.0)
    return factor


def build_mock_damage_preview(selection: MockIntakeSelection) -> MockDamagePreview:
    total_area_m2 = sum(selection.floor_areas) if selection.scope == "Entire building" else float(selection.unit_area_m2 or 0.0)
    factor = _typology_factor(selection.use, selection.subtype, selection.specific_type)
    structural_max = round(total_area_m2 * factor * 165.0, 2)
    content_max = round(total_area_m2 * factor * 95.0, 2)
    inventory_enabled = selection.use != "Residential"
    inventory_max = round(total_area_m2 * factor * 72.0, 2) if inventory_enabled else None
    shared_structural_damage = round(structural_max * (selection.shared_damage_pct / 100.0), 2)
    return MockDamagePreview(
        total_area_m2=round(total_area_m2, 2),
        structural_max=structural_max,
        content_max=content_max,
        inventory_max=inventory_max,
        inventory_enabled=inventory_enabled,
        shared_structural_damage=shared_structural_damage,
    )


def _make_function_metadata(
    *,
    function_id: int,
    function_type: SSMFunctionType,
    name: str,
    use: str,
    subtype: str,
    specific_type: str | None,
) -> SSMFunctionMetadata:
    l1_category, l2_category, l3_categories = resolve_typology_categories(use, subtype, specific_type)
    return SSMFunctionMetadata(
        id=function_id,
        function_type=function_type,
        name=name,
        model=DamageModel.CUSTOM,
        country=Country.NLD,
        l1_category=l1_category,
        l2_categories=[l2_category],
        l3_categories=l3_categories,
        method=SSMFunctionMethod.EXPERT_CALCULATION,
        scale=SSMFunctionScale.MESO,
        notes="Mock data used for frontend testing.",
        source_description="Generated by the mock intake flow.",
    )


def _make_function(
    *,
    function_id: int,
    function_type: SSMFunctionType,
    name: str,
    use: str,
    subtype: str,
    specific_type: str | None,
) -> SSMFunction:
    metadata = _make_function_metadata(
        function_id=function_id,
        function_type=function_type,
        name=name,
        use=use,
        subtype=subtype,
        specific_type=specific_type,
    )
    return SSMFunction(
        metadata=metadata,
        values={0.0: 0.0, 1.0: 1.0},
        intensity_unit=IntensityUnit.DEPTH_METERS,
    )


def build_mock_result_payload(selection: MockIntakeSelection, building: MockBuildingContext) -> MockResultPayload:
    preview = build_mock_damage_preview(selection)
    package_name = " / ".join(
        part for part in [selection.use, selection.subtype, selection.specific_type] if part
    )

    function_types = [SSMFunctionType.STRUCTURE, SSMFunctionType.CONTENT]
    if preview.inventory_enabled:
        function_types.append(SSMFunctionType.INVENTORY)

    functions: list[SSMFunction] = []
    function_metadata: dict[int, SSMFunctionMetadata] = {}
    ead_row: dict[str, Any] = {
        "osm_id": building.building_id,
        "geometry": building.polygon,
        "object_type": package_name,
    }

    function_values = [preview.structural_max * 0.62, preview.content_max * 0.58]
    if preview.inventory_enabled and preview.inventory_max is not None:
        function_values.append(preview.inventory_max * 0.6)

    for index, (function_type, function_value) in enumerate(zip(function_types, function_values, strict=False), start=1):
        function = _make_function(
            function_id=index,
            function_type=function_type,
            name=package_name,
            use=selection.use,
            subtype=selection.subtype,
            specific_type=selection.specific_type,
        )
        functions.append(function)
        function_metadata[function.metadata.id] = function.metadata
        ead_row[str(function.metadata.id)] = round(function_value, 2)

    package = DamageFunctionPackage(functions)

    risk_profile_data = {
        building.building_id: [
            (10, round(preview.total_area_m2 * 0.01, 2)),
            (25, round(preview.total_area_m2 * 0.015, 2)),
            (50, round(preview.total_area_m2 * 0.02, 2)),
            (100, round(preview.total_area_m2 * 0.026, 2)),
            (250, round(preview.total_area_m2 * 0.033, 2)),
            (500, round(preview.total_area_m2 * 0.041, 2)),
            (1000, round(preview.total_area_m2 * 0.05, 2)),
        ]
    }

    return MockResultPayload(
        ead=pd.DataFrame([ead_row]),
        damage_functions={package.metadata.name: package.ids},
        all_packages={package.metadata.name: package},
        function_metadata=function_metadata,
        risk_profile_data=risk_profile_data,
    )
