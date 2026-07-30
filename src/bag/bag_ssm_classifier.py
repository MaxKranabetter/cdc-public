import logging

import pandas as pd

from src.calc.models import BuildingClass, BuildingData
from src.bag.models import VerblijfsobjectFeature
from src.ssm.models import DamageFunctionPackage
from shapely.wkt import loads
from shapely.geometry import Polygon, shape
import json

BAG_TO_MAIN_CATEGORY = {
    'kantoorfunctie': BuildingClass.OFFICE,
    'winkelfunctie': BuildingClass.COMMERCIAL,
    'bijeenkomstfunctie': BuildingClass.OTHER,
    'logiesfunctie': BuildingClass.OTHER,
    'onderwijsfunctie': BuildingClass.OTHER,
    'gezondheidszorgfunctie': BuildingClass.OTHER,
    'sportfunctie': BuildingClass.OTHER,
    'celfunctie': BuildingClass.OTHER,
    'industriefunctie': BuildingClass.INDUSTRIAL,
    'overige gebruiksfunctie': BuildingClass.OTHER
}

def get_vbo_area(target_doel: str, vbos: list[VerblijfsobjectFeature]) -> float:
    """Calculates the total oppervlakte for a specific gebruiksdoel across all num_vbos."""
    if not vbos:
        return 0.0
    total = 0.0
    for vbo in vbos:
        unit_doelen = [d.strip() for d in (vbo.properties.gebruiksdoel or "").split(',')]
        if target_doel in unit_doelen:
            total += (vbo.properties.oppervlakte or 0)
    return total

class BAGSSMClassifier:
    
    def __init__(self, damage_functions: dict[tuple[int], DamageFunctionPackage]):
        self.damage_functions = damage_functions
        
    def _safe_load_geom(self, geom: str | Polygon) -> Polygon | None:
        if isinstance(geom, Polygon):
            return geom
        if not geom:
            return None
        try:
            if geom.strip().startswith('{'):
                geom_dict = json.loads(geom)
                return shape(geom_dict)
            else:
                return loads(geom)
        except Exception as e:
            logging.error(f"Error parsing geometry string: {e}")
            return None

    def get_sqm_from_geometry(self, geometry: str | Polygon) -> float:
        """Extract square meters from geometry string (WKT or GeoJSON format)."""
        parsed_geom = self._safe_load_geom(geometry)
        if parsed_geom is None:
            return 0.0
        return parsed_geom.area

    def classify_gebruiksdoel_to_category(self, gebruiksdoel: str) -> BuildingClass:
        return BAG_TO_MAIN_CATEGORY.get(gebruiksdoel, BuildingClass.OTHER)
    
    def _get_most_common_doel(self, doelen: list[str], verblijfsobjecten: list[VerblijfsobjectFeature]) -> str | None:
        doel_areas = {doel: get_vbo_area(doel, verblijfsobjecten) for doel in doelen}
        if not doel_areas:
            return None
        return max(doel_areas, key=doel_areas.get)
    
    def _get_secondary_class(self, doelen: list[str], floors: int, verblijfsobjecten: list) -> BuildingClass | None:
        secondary_doelen = [d for d in doelen if d != "woonfunctie"]
        secondary_class = None
        if secondary_doelen and floors > 1:
            # choose most common, weighted by area
            most_common_secondary_doel = self._get_most_common_doel(secondary_doelen, verblijfsobjecten)
            if most_common_secondary_doel:
                secondary_class = self.classify_gebruiksdoel_to_category(most_common_secondary_doel)
        return secondary_class

    def match_bag_object_to_building_class(self, bag_data: pd.Series) -> tuple[BuildingClass, BuildingClass | None]:
        doelen = bag_data.get('gebruiksdoel', '').split(',')
        vbos = bag_data.get('verblijfsobjecten', [])
        num_vbos=bag_data.get('aantal_verblijfsobjecten', len(vbos))
        verblijfsobjecten=vbos
        floors = bag_data['building_floors']
        main_function = self._get_most_common_doel(doelen, verblijfsobjecten)

        if "woonfunctie" in doelen: # if there is any residential use, we classify as residential, and then check for secondary use
            return (BuildingClass.SINGLE_UNIT_RESIDENTIAL, None) if num_vbos < 2 else (BuildingClass.MULTI_UNIT_RESIDENTIAL, self._get_secondary_class(doelen, floors, verblijfsobjecten))

        if main_function == "kantoorfunctie":
            return (BuildingClass.OFFICE, self._get_secondary_class(doelen, floors, verblijfsobjecten))
        
        if main_function == "winkelfunctie":
            return (BuildingClass.COMMERCIAL, self._get_secondary_class(doelen, floors, verblijfsobjecten))

        if main_function == "industriefunctie":
            return (BuildingClass.INDUSTRIAL, None) # assume no mixed use for industrial buildings
        
        return (BuildingClass.OTHER, None)

    def _normalize(self, scores_dict: dict) -> dict:
        total = sum(scores_dict.values())
        if total > 0:
            return {k: v / total for k, v in scores_dict.items() if v > 0}
        return {}
    
    def determine_building_data(self, name: str, bag_data: pd.Series, address: str) -> BuildingData:
        main_class, unique_ground_floor_class = self.match_bag_object_to_building_class(bag_data)
        return BuildingData(
            name=name,
            polygon=bag_data.geometry,
            building_class=main_class,
            num_units=len(bag_data.get('verblijfsobjecten', [])),
            unique_ground_floor_class=unique_ground_floor_class,
            floor_count=bag_data.get('building_floors', 1) or 1,
            input_address=address
        )