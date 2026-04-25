from dataclasses import dataclass
from enum import Enum

import geopandas as gpd


class BuildingClassifierType(Enum):
    BAG = "BAG"

@dataclass
class BuildingDataInput:
    building_classifier_type: BuildingClassifierType

    name: str | None = None

    address: str | None = None
    shapefile_path: str | None = None
    geodataframe: gpd.GeoDataFrame | None = None


@dataclass
class DamageScannerInputs:
    building_inputs: list[BuildingDataInput]
    max_damage_function_suggestions_per_building: int = 5
    override_floodmaps: dict[int, str] | None = None