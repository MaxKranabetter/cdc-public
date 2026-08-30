from dataclasses import dataclass
from enum import Enum
from typing import Literal

import geopandas as gpd
from pydantic import BaseModel, ConfigDict, field_serializer, model_validator
import shapely

class BuildingClassifierType(Enum):
    BAG = "BAG"

class BuildingClass(Enum):
    """Building typologies that we use to determine the correct damage functions."""
    SINGLE_UNIT_RESIDENTIAL = "single_unit_residential"
    MULTI_UNIT_RESIDENTIAL = "multi_unit_residential"
    INDUSTRIAL = "industrial"
    COMMERCIAL = "commercial"
    OFFICE = "office"
    OTHER = "other"

@dataclass
class BuildingDataInput:
    name: str | None = None

    address: str | None = None
    shapefile_path: str | None = None
    geodataframe: gpd.GeoDataFrame | None = None

    building_classifier_type: BuildingClassifierType | None = None
    building_class: BuildingClass | None = None

    def __init__(self,
        name: str | None = None,
        address: str | None = None,
        shapefile_path: str | None = None,
        geodataframe: gpd.GeoDataFrame | None = None,
        building_classifier_type: BuildingClassifierType | None = None,
        building_class: BuildingClass | None = None):
        if building_classifier_type is None and building_class is None:
            raise ValueError("Either building_classifier_type or building_class must be provided")

        self.name = name
        self.address = address
        self.shapefile_path = shapefile_path
        self.geodataframe = geodataframe
        self.building_classifier_type = building_classifier_type
        self.building_class = building_class

@dataclass
class CDCInputs:
    building_input: BuildingDataInput
    is_overlast: bool = False
    is_overstroming: bool = True
    override_floodmaps: dict[int, str] | None = None

    @model_validator(mode="after")
    def check_flood_type(cls, values):
        is_overlast = values.get("is_overlast", False)
        is_overstroming = values.get("is_overstroming", True)
        if is_overlast == is_overstroming:
            raise ValueError("Exactly one of is_overlast or is_overstroming must be True")
        return values

class BuildingData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    crs: str
    polygon: shapely.geometry.Polygon = None
    building_class: BuildingClass
    input_address: str | None = None
    
    floor_count: int = 1
    num_units: int = 1
    unique_ground_floor_class: BuildingClass | None = None

    @model_validator(mode="before")
    def check_unique_ground_floor_class(cls, values):
        floor_count = values.get("floor_count", 1)
        unique_ground_floor_class = values.get("unique_ground_floor_class")
        if unique_ground_floor_class is not None and floor_count <= 1:
            raise ValueError("unique_ground_floor_class can only be set if floor_count > 1")
        return values

    @field_serializer('polygon')
    def serialize_polygon(self, polygon: shapely.geometry.Polygon, _info):
        if polygon is None:
            return None
        # Converts the Shapely object to a GeoJSON dictionary
        return shapely.geometry.mapping(polygon)

class FloodDepth(BaseModel):
    unit: Literal["m"] = "m"
    value: float = 0.0
    area_coverage: float = 0.0


class DamageEstimate(BaseModel):
    damage_description: str
    price_level_year: int
    ssm_function_id: int
    currency: Literal["EUR"] = "EUR"
    value: float = 0.0
    absolute_maximum_damage: float = 0.0

    warnings: list[str] = []

    @classmethod
    @staticmethod
    def from_multiple(cls, damage_estimates: list["DamageEstimate"]) -> "DamageEstimate":
        if not damage_estimates:
            raise ValueError("No damage estimates provided")

        warnings = []
        total_damage_value = sum(damage.value for damage in damage_estimates)
        for damage in damage_estimates:
            if damage.warnings:
                warnings.extend([f"{damage.damage_description}: {warning}" for warning in damage.warnings])
        return DamageEstimate(
            damage_description="Total Damage",
            currency="EUR",
            value=total_damage_value,
            warnings=warnings,
            price_level_year=max(damage.price_level_year for damage in damage_estimates),
            absolute_maximum_damage=sum(damage.absolute_maximum_damage for damage in damage_estimates)
        )

class FloodEvent(BaseModel):
    return_period: int
    unique_flood_depths: list[FloodDepth]
    all_damages: list[DamageEstimate]

    @property
    def weighted_flood_height(self) -> float:
        total_coverage = sum(depth.area_coverage for depth in self.unique_flood_depths)
        if total_coverage == 0:
            return 0.0
        weighted_sum = sum(depth.value * depth.area_coverage for depth in self.unique_flood_depths)
        return weighted_sum / total_coverage

    @property
    def total_damage(self) -> DamageEstimate:
        return DamageEstimate.from_multiple(self.all_damages)

class CDCOutput(BaseModel):
    building: BuildingData
    flood_events_considered: list[FloodEvent]
    annualised_expected_damages: list[DamageEstimate]

    warnings: list[str] = []
    is_overlast: bool = False
    is_overstroming: bool = True

    @property
    def total_annualised_expected_damage(self) -> DamageEstimate:
        return DamageEstimate.from_multiple(self.annualised_expected_damages)