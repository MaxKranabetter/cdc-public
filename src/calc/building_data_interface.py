import os
import tempfile
import pandas as pd

from src.calc.damage_function_interface import DamageFunctionInterface
from src.calc.models import BuildingDataInput
from src.common.build_shapefile import create_gdf

import geopandas as gpd

from src.bag.get_building_polygon import get_building_polygons_from_address, get_3d_bag_data_for_pand


class BuildingDataInterface:

    def __init__(
        self,
        input: BuildingDataInput,
        function_interface: DamageFunctionInterface,
        warnings: dict[str, list[str]],
        building_classifier_column: str = 'object_type',
        coverage_floodmap_path: str | None = None,
    ):
        self.input = input
        self.functions = function_interface
        self.building_classifier_column = building_classifier_column
        self.coverage_floodmap_path = coverage_floodmap_path
        self.warnings = warnings

    def _get_address_data(self, address: str, is_overlast: bool) -> gpd.GeoDataFrame:
        building_data, neighbourhood = get_building_polygons_from_address(
            address,
            response_limit=25,
            search_box_size=50,
            coverage_floodmap_path=self.coverage_floodmap_path,
            is_overlast=is_overlast,
        )
        bag_3d_data = get_3d_bag_data_for_pand(building_data.pand.properties.identificatie)
        properties = building_data.pand.properties.model_dump()
        properties["building_floors"] = self.get_floor_count_from_3d_bag_data(building_data.pand.properties.identificatie, bag_3d_data)
        properties["neighbourhood"] = neighbourhood
        properties["verblijfsobjecten"] = building_data.verblijfsobjecten
        return create_gdf(building_data.pand.geometry.coordinates, properties, crs="EPSG:28992") # RD New

    def get_floor_count_from_3d_bag_data(self, pand_id: str, bag_3d_data: dict) -> int:
        try:
            city_objects = bag_3d_data["feature"]["CityObjects"]
            if f"NL.IMBAG.Pand.{pand_id}" not in city_objects:
                raise ValueError(f"Pand ID {pand_id} not found in 3D BAG data")
            return city_objects[f"NL.IMBAG.Pand.{pand_id}"]["attributes"]["b3_bouwlagen"]
        except:
            raise ValueError(f"Invalid 3D BAG data: {bag_3d_data}")

    def _load_shapefile_data(self, shapefile_path: str) -> gpd.GeoDataFrame:
        return gpd.read_file(shapefile_path)
    
    def match_classifier_column(self, gdf: gpd.GeoDataFrame, classifier_column: str, id: str, function_ids: list[str]) -> gpd.GeoDataFrame:
        if "osm_id" not in gdf.columns:
            gdf["osm_id"] = id # damagescanner requires this column to function, we can use it to easily identify buildings in the final output
        gdf["classifier_used"] = classifier_column        
        gdf['temp_functions_list'] = gdf.apply(lambda x: function_ids, axis=1)
        gdf = gdf.explode('temp_functions_list', ignore_index=True) # just calculate the values for all damage functions so that we can easily use them later without having to recalculate
        gdf[self.building_classifier_column] = gdf['temp_functions_list']
        gdf = gdf.drop(columns=['temp_functions_list'])

        return gdf

    def _load_input(self, input: BuildingDataInput, is_overlast: bool) -> gpd.GeoDataFrame:
        if input.address is not None:
            gdf = self._get_address_data(input.address, is_overlast=is_overlast)
        elif input.shapefile_path is not None:
            gdf = self._load_shapefile_data(input.shapefile_path)
        elif input.geodataframe is not None:
            gdf = input.geodataframe
        else:
            raise ValueError("Invalid building data input: must provide either address, shapefile path, or geodataframe")
        return gdf

    def get_building_gdf(self, is_overlast: bool) -> str | gpd.GeoDataFrame:
        """
        Loads and processes building data from the provided inputs, and stores it in a Shapefile in a temporary directory.
        Returns the path to the Shapefile.
        """
        all_building_data = self._load_input(self.input, is_overlast=is_overlast)
        return all_building_data

        # if not as_fp:
        #     return all_building_data
        
        # temp_dir = tempfile.mkdtemp()
        # tmp_shapefile_path = os.path.join(temp_dir, "combined_building_data.shp")
        # all_building_data.to_file(tmp_shapefile_path, driver='ESRI Shapefile')
        # return tmp_shapefile_path