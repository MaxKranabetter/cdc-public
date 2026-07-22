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

    sbi_code: str | None = None

    def __init__(self,
        name: str | None = None,
        address: str | None = None,
        shapefile_path: str | None = None,
        geodataframe: gpd.GeoDataFrame | None = None,
        sbi_code: str | None = None,
        building_classifier_type: BuildingClassifierType | None = None,
        building_class: BuildingClass | None = None):
        if building_classifier_type is None and building_class is None:
            raise ValueError("Either building_classifier_type or building_class must be provided")

        self.name = name
        self.address = address
        self.sbi_code = sbi_code
        self.shapefile_path = shapefile_path
        self.geodataframe = geodataframe
        self.building_classifier_type = building_classifier_type
        self.building_class = building_class

@dataclass
class CDCInputs:
    building_input: BuildingDataInput
    override_floodmaps: dict[int, str] | None = None

class BuildingData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    polygon: shapely.geometry.Polygon = None
    building_class: BuildingClass
    
    floor_count: int = 1
    num_units: int = 1
    sbi_code: str | None = None
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
    currency: Literal["EUR"] = "EUR"
    value: float = 0.0

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
            price_level_year=max(damage.price_level_year for damage in damage_estimates)
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

    @property
    def total_annualised_expected_damage(self) -> DamageEstimate:
        return DamageEstimate.from_multiple(self.annualised_expected_damages)