from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
import random
import tempfile
import pandas as pd

from src.bag.bag_ssm_classifier import BAGSSMClassifier
from src.calc.file_mapping import DEFAULT_FLOODMAPS, FloodScenario
from src.common.build_shapefile import create_gdf
from damagescanner.core import DamageScanner

import geopandas as gpd

from src.bag.get_building_polygon import get_building_polygons_from_address
from src.ssm.models import IntensityUnit, L1FunctionCategory, SSMFunction, SSMFunctionMetadata, SSMFunctionType
from src.ssm.ssm_function_loader import get_function_from_id, load_ssm_functions

class MaxDamageInterface:

    def __init__(self, object_col: str = 'obj_type'):
        self.object_col = object_col
        self.max_damages_per_sqm = {
            L1FunctionCategory.EMPLOYMENT: {
                SSMFunctionType.STRUCTURE: 580.5,
                SSMFunctionType.CONTENT: 580.5,
                SSMFunctionType.COMBINED: 1161,
                SSMFunctionType.INVENTORY: 580.5 # placeholder
            },
            L1FunctionCategory.RESIDENTIAL: {
                SSMFunctionType.STRUCTURE: 561,
                SSMFunctionType.CONTENT: 281,
                SSMFunctionType.COMBINED: 842
            },
            L1FunctionCategory.MULTIPLE: {
                SSMFunctionType.STRUCTURE: 0, # placeholde
                SSMFunctionType.CONTENT: 0, # TODO: implement
                SSMFunctionType.COMBINED: 0
            },
            L1FunctionCategory.INFRASTRUCTURE: {
                SSMFunctionType.STRUCTURE: 0, # placeholde
                SSMFunctionType.CONTENT: 0, # TODO: implement
                SSMFunctionType.COMBINED: 0
            },
            L1FunctionCategory.OTHER: {
                SSMFunctionType.STRUCTURE: 0, # placeholde
                SSMFunctionType.CONTENT: 0, # TODO: implement
                SSMFunctionType.COMBINED: 0
            }
        }

    def get_max_damage_per_sqm_for_function(self, function: SSMFunction) -> float:
        # TODO: logic needs to be refined
        damage = self.max_damages_per_sqm.get(function.metadata.l1_category, {}).get(function.metadata.function_type)
        if damage is None:
            raise ValueError(f"No max damage per sqm found for function with L1 category {function.metadata.l1_category} and function type {function.metadata.function_type}")
        return damage
    
    def get_max_damage_data(self, selected_curves: list[SSMFunction]) -> pd.DataFrame:
        maxdam_dict = {str(curve.metadata.id): self.get_max_damage_per_sqm_for_function(curve) for curve in selected_curves}
        return pd.DataFrame.from_dict(maxdam_dict, orient='index').reset_index().rename(columns={'index': self.object_col, 0: 'damage'})

class DamageFunctionInterface:

    def __init__(self):
        self.function_confidences = {}
        self.damage_function_metadata: dict[int, SSMFunctionMetadata] = load_ssm_functions()
        self.filter_damage_functions()
        self.bag_ssm_classifier = BAGSSMClassifier(self.damage_function_metadata)

    def get_depth_value(self, depth: float, function: SSMFunction) -> float:
        if depth in function.values:
            return function.values[depth]
        else:
            # interpolate value
            sorted_depths = sorted(function.values.keys())
            for index, depth_value in enumerate(sorted_depths):
                if depth > depth_value:
                    if index == 0:
                        return function.values[depth_value]
                    else:
                        lower_value = function.values[sorted_depths[index-1]]
                        upper_value = function.values[depth_value]
                        # linear interpolation
                        depth_diff = depth_value - sorted_depths[index-1]
                        value_diff = upper_value - lower_value
                        percent_diff = (depth - sorted_depths[index-1]) / depth_diff
                        if depth_diff == 0:
                            return lower_value
                        else:
                            return lower_value + (percent_diff * value_diff)
        return float('nan')

    def filter_damage_functions(self) -> dict[str, SSMFunction]:
        useable_curves: list[SSMFunction] = []
        for metadata in self.damage_function_metadata.values():
            curve = get_function_from_id(metadata.id)
            if curve is None:
                logging.warning(f"Could not load curve with ID {metadata.id} and name {metadata.name}")
                continue
            if curve.intensity_unit != IntensityUnit.DEPTH_METERS:
                logging.warning(f"Skipping curve {curve.metadata.name} with unsupported intensity unit {curve.intensity_unit}")
                continue
            useable_curves.append(curve)
        if len(useable_curves) == 0:
            raise ValueError("No useable curves found with intensity unit in depth meters.")
        self.damage_functions = {str(curve.metadata.id): curve for curve in useable_curves}
        return self.damage_functions

    def get_damage_functions(self) -> pd.DataFrame:
        curves_to_include = [curve for curve in self.damage_functions.values() if str(curve.metadata.id) in self.function_confidences]
        column_headers = ["Depth"] + [str(curve.metadata.id) for curve in curves_to_include]
        depth_values = list(curves_to_include)[0].values.keys() # this assumes all curves have the same depth values, which should be the case for SSM functions - this could do with a cleaner logic that includes rescaling though
        data = []
        for depth in depth_values:
            row = [depth] + [self.get_depth_value(depth, curve) for curve in curves_to_include]
            data.append(row)
        return pd.DataFrame(data, columns=column_headers)
    
    def classify_bag_landuse(self, bag_data: pd.Series) -> list[SSMFunction]:
        functions_with_confidences = self.bag_ssm_classifier.match_functions_to_bag_object(bag_data, max_functions=5)
        for func_meta, confidence in functions_with_confidences:
            self.function_confidences[str(func_meta.id)] = confidence
        return [self.damage_functions[str(func_meta.id)] for func_meta, confidence in functions_with_confidences]
    
    def get_matching_functions_for_object(self, row: pd.Series) -> list[SSMFunction]:
        if row["classifier_used"] == BuildingClassifierType.BAG.value:
            return self.classify_bag_landuse(row)
        funcs = [random.choice(list(self.damage_functions.values())), random.choice(list(self.damage_functions.values()))]
        for func in funcs:
            self.function_confidences[str(func.metadata.id)] = 0
        return funcs

class BuildingClassifierType(Enum):
    BAG = "BAG"

@dataclass
class BuildingDataInput:
    building_classifier_type: BuildingClassifierType

    name: str | None = None

    address: str | None = None
    shapefile_path: str | None = None
    geodataframe: gpd.GeoDataFrame | None = None

class BuildingDataInterface:

    def __init__(
        self,
        inputs: list[BuildingDataInput],
        function_interface: DamageFunctionInterface,
        building_classifier_column: str = 'object_type',
        coverage_floodmap_path: str | None = None,
    ):
        self.inputs = inputs
        self.functions = function_interface
        self.building_classifier_column = building_classifier_column
        self.coverage_floodmap_path = coverage_floodmap_path
        assert len(inputs) > 0, "At least one building data input must be provided"

    def _get_address_data(self, address: str) -> gpd.GeoDataFrame:
        building_data, neighbourhood = get_building_polygons_from_address(
            address,
            response_limit=25,
            search_box_size=50,
            coverage_floodmap_path=self.coverage_floodmap_path,
        )
        properties = building_data.pand.properties.model_dump()
        properties["neighbourhood"] = neighbourhood
        properties["verblijfsobjecten"] = building_data.verblijfsobjecten
        return create_gdf(building_data.pand.geometry.coordinates, properties, crs="EPSG:28992") # RD New

    def _load_shapefile_data(self, shapefile_path: str) -> gpd.GeoDataFrame:
        return gpd.read_file(shapefile_path)
    
    def _match_classifier_column(self, gdf: gpd.GeoDataFrame, classifier_column: str, id: str) -> gpd.GeoDataFrame:
        if "osm_id" not in gdf.columns:
            gdf["osm_id"] = id # damagescanner requires this column to function, we can use it to easily identify buildings in the final output
        gdf["classifier_used"] = classifier_column
        def _get_function_names(row):
            matching_functions = self.functions.get_matching_functions_for_object(row)
            function_names = [str(func.metadata.id) for func in matching_functions]
            if len(function_names) == 0:
                raise ValueError(f"No matching damage functions found for feature: {row}")
            return function_names
        
        gdf['temp_functions_list'] = gdf.apply(_get_function_names, axis=1)
        gdf = gdf.explode('temp_functions_list', ignore_index=True)
        gdf[self.building_classifier_column] = gdf['temp_functions_list']
        gdf = gdf.drop(columns=['temp_functions_list'])

        return gdf

    def _load_input(self, input: BuildingDataInput, index: int) -> gpd.GeoDataFrame:
        if input.address is not None:
            gdf = self._get_address_data(input.address)
        elif input.shapefile_path is not None:
            gdf = self._load_shapefile_data(input.shapefile_path)
        elif input.geodataframe is not None:
            gdf = input.geodataframe
        else:
            raise ValueError("Invalid building data input: must provide either address, shapefile path, or geodataframe")
        return self._match_classifier_column(gdf, input.building_classifier_type.value, input.name or f"building_{index+1}")

    def get_building_data(self, as_fp: bool = True) -> str | gpd.GeoDataFrame:
        """
        Loads and processes building data from the provided inputs, and stores it in a Shapefile in a temporary directory.
        Returns the path to the Shapefile.
        """
        all_building_data = [self._load_input(input, index) for index, input in enumerate(self.inputs)]
        combined_gdf = gpd.GeoDataFrame(pd.concat(all_building_data, ignore_index=True), crs=all_building_data[0].crs)

        if not as_fp:
            return combined_gdf
        
        temp_dir = tempfile.mkdtemp()
        tmp_shapefile_path = os.path.join(temp_dir, "combined_building_data.shp")
        combined_gdf.to_file(tmp_shapefile_path, driver='ESRI Shapefile')
        
        return tmp_shapefile_path

class FloodmapInterface:

    def __init__(self, override_floodmaps: dict[int, str] | None = None):
        floodmaps = DEFAULT_FLOODMAPS[FloodScenario.BASELINE] if override_floodmaps is None else override_floodmaps
        self.available_floodmaps = self._resolve_floodmap_paths(floodmaps)

    def _resolve_floodmap_paths(self, floodmaps: dict[int, str]) -> dict[int, str]:
        project_root = Path(__file__).resolve().parents[2]
        resolved_paths: dict[int, str] = {}
        for return_period, floodmap_path in floodmaps.items():
            path_obj = Path(floodmap_path)
            resolved_paths[return_period] = str(path_obj if path_obj.is_absolute() else project_root / path_obj)
        return resolved_paths

    def get_base_floodmap_data(self) -> str:
        # for now we just return the path to the base floodmap data, but this could be extended to include logic for selecting different floodmaps based on user input, or for loading the floodmap data into memory if needed
        return self.available_floodmaps[1000]
    
    def get_floodmap_dict(self) -> dict[int, str]:
        return self.available_floodmaps

    def get_representative_floodmap_path(self) -> str:
        if len(self.available_floodmaps) == 0:
            raise ValueError("No floodmaps are configured for coverage validation.")

        preferred_return_periods = [100000, 10000, 1000, 100, 10]
        for return_period in preferred_return_periods:
            if return_period in self.available_floodmaps:
                return self.available_floodmaps[return_period]

        first_key = sorted(self.available_floodmaps.keys())[0]
        return self.available_floodmaps[first_key]

@dataclass
class DamageScannerInputs:
    building_inputs: list[BuildingDataInput]
    max_damage_function_suggestions_per_building: int = 5
    override_floodmaps: dict[int, str] | None = None

class DamageScannerInterface:

    def __init__(self, inputs: DamageScannerInputs):
        self.damage_scanner = None
        self.object_col = 'object_type' # this should be the name of the column in the building data that contains the object/landuse type, which is used to link to the damage curves
        self.damage_function_interface = DamageFunctionInterface()
        self.floodmap_interface = FloodmapInterface(override_floodmaps=inputs.override_floodmaps)
        self.building_data_interface = BuildingDataInterface(
            inputs.building_inputs,
            function_interface=self.damage_function_interface,
            coverage_floodmap_path=self.floodmap_interface.get_representative_floodmap_path(),
        )
        self.max_damage_interface = MaxDamageInterface(object_col=self.object_col)

    def _init_damage_scanner(self) -> DamageScanner:
        if self.damage_scanner is not None:
            return self.damage_scanner
        building_data = self.building_data_interface.get_building_data(as_fp=False)
        damage_functions = self.damage_function_interface.get_damage_functions()
        max_damage_data = self.max_damage_interface.get_max_damage_data(
            selected_curves=[curve for curve in self.damage_function_interface.damage_functions.values() if str(curve.metadata.id) in damage_functions.columns[1:]]
        )
        floodmap_data = self.floodmap_interface.get_base_floodmap_data()
        
        self.damage_scanner = DamageScanner(floodmap_data, building_data, damage_functions, max_damage_data)
        return self.damage_scanner

    def _get_ead(self) -> pd.DataFrame | None:
        ds = self._init_damage_scanner()
        floodmap_dict = self.floodmap_interface.get_floodmap_dict()
        return ds.risk(floodmap_dict)#, object_col=self.object_col) # type: ignore
    
    def get_damages(self) -> gpd.GeoDataFrame:
        ead = self._get_ead()

        # convert risk value to annualised damages
        building_geometries = ead.set_index("osm_id").geometry.to_dict()
        building_areas = {osm_id: geom.area for osm_id, geom in building_geometries.items()}
        ead["annualised_damage"] = ead.apply(lambda row: row["risk"] * building_areas.get(row["osm_id"], 0), axis=1)
        ead.pop("risk")

        # pivot data
        # input format: osm_id (building ID), obj_type (damage function), geometry, risk
        # output format: osm_id, {unique obj_type values as columns}, geometry, risk
        damage_data = ead.pivot_table(index=['osm_id', 'geometry'], columns='object_type', values='annualised_damage').reset_index()
        damage_data["average_ead"] = damage_data[[col for col in damage_data.columns if col not in ['osm_id', 'geometry']]].mean(axis=1, skipna=True)
        damage_gdf = gpd.GeoDataFrame(damage_data, geometry='geometry', crs=ead.crs)
        return damage_gdf