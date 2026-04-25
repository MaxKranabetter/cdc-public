import os
import tempfile
import pandas as pd

from src.calc.damage_function_interface import DamageFunctionInterface
from src.calc.models import BuildingDataInput
from src.common.build_shapefile import create_gdf

import geopandas as gpd

from src.bag.get_building_polygon import get_building_polygons_from_address


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