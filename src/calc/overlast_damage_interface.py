from pathlib import PurePath, Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import xarray as xr

from src.calc.damage_function_interface import get_depth_value
from src.calc.models import BuildingData
from src.ssm.models import SSMFunction

BUILDING_BUFFER_DISTANCE = 1.0  # in meters, buffer around building polygon to sample floodmap values

RASTER_HEIGHT_TRANSLATIONS = {
    0: 0.0,  # No water
    1: 0.2,  # 0.1 - 0.3
    2: 0.4,  # 0.3 - 0.5
    3: 0.75,  # 0.5 - 1.0
    4: 1.5,  # 1.0 - 2.0
    5: 2.0,  # 2.0+ (this is a limitation of the data)
}

class OverlastDamageInterface:

    def __init__(self, building_data: BuildingData, floodmap: str | Path | pd.DataFrame):
        self.building = building_data
        self.floodmap_input = floodmap
        self.floodmap = self.load_floodmap()

    def load_floodmap(self) -> pd.DataFrame:
        if isinstance(self.floodmap_input, pd.DataFrame):
            return self.floodmap_input
        if isinstance(self.floodmap_input, str):
            self.floodmap_input = Path(self.floodmap_input)
        # copied from DamageScanner code
        if isinstance(self.floodmap_input, PurePath):
            if self.floodmap_input.suffix in [".tif", ".tiff", ".nc"]:
                floodmap = xr.open_dataset(self.floodmap_input, engine="rasterio")
                if self.floodmap_input.suffix in (".tif", ".tiff"):
                    assert floodmap.band.size == 1, (
                        "floodmap data should only contain one band. If you have multiple bands, please select one band using the `band` argument."
                    )
                    floodmap = floodmap["band_data"].sel(band=1)
                self.floodmap_crs = floodmap.rio.crs

            elif self.floodmap_input.suffix in [".shp", ".gpkg"]:
                floodmap = gpd.read_file(self.floodmap_input)
                self.floodmap_crs = floodmap.crs
            elif self.floodmap_input.suffix == ".parquet":
                floodmap = gpd.read_parquet(self.floodmap_input)
                self.floodmap_crs = floodmap.crs
            else:
                raise ValueError(
                    "floodmap data should either be a geotiff, netcdf, shapefile, geopackage or parquet file"
                )
        elif isinstance(self.floodmap_input, rasterio.io.DatasetReader):
            floodmap = self.floodmap_input.copy()
            self.floodmap_crs = floodmap.crs
        elif isinstance(self.floodmap_input, (xr.Dataset, xr.DataArray)):
            floodmap = self.floodmap_input.copy()
            self.floodmap_crs = floodmap.rio.crs

        elif isinstance(self.floodmap_input, gpd.GeoDataFrame):
            floodmap = self.floodmap_input.copy()
            self.floodmap_crs = floodmap.crs
        else:
            raise ValueError(
                f"floodmap should be a raster or GeoDataFrame object, {type(self.floodmap_input)} given"
            )
        return floodmap

    def get_flood_height(self, percentile: int = 90) -> float | None:
        if self.building.polygon is None:
            return None

        # 1. Make sure raster floodmap and vector building polygon are in the same CRS
        # Wrap the shapely polygon in a GeoDataFrame to handle CRS transformation
        building_gdf = gpd.GeoDataFrame(geometry=[self.building.polygon], crs=self.building.crs)
        
        if str(self.building.crs) != str(self.floodmap_crs):
            building_gdf = building_gdf.to_crs(self.floodmap_crs)

        # 2. Create a 1m buffer around the building polygon (assuming single object)
        buffered_geom = building_gdf.geometry.iloc[0].buffer(BUILDING_BUFFER_DISTANCE)

        # 3 & 4. Sample all raster values within this buffer and return the highest value found
        if isinstance(self.floodmap, (xr.DataArray, xr.Dataset)):
            clipped = self.floodmap.rio.clip([buffered_geom], self.floodmap_crs, all_touched=True)
            if isinstance(clipped, xr.Dataset):
                clipped = clipped[list(clipped.data_vars)[0]]
            
            # Calculate the X'th percentile using xarray's quantile (expects q between 0 and 1)
            q = percentile / 100.0
            val = clipped.quantile(q, skipna=True).values
            if np.isnan(val):
                return None
            max_val = int(val)
        elif isinstance(self.floodmap, rasterio.io.DatasetReader):
            raise NotImplementedError("Sampling from rasterio DatasetReader is not yet tested.")
            out_image, _ = rasterio.mask.mask(
                self.floodmap, [buffered_geom], crop=True, all_touched=True
            )
            nodata = self.floodmap.nodatavals[0]
            valid_vals = out_image[out_image != nodata] if nodata is not None else out_image
            if valid_vals.size == 0:
                return None
            max_val = int(valid_vals.max())
        else:
            raise TypeError("Unsupported floodmap raster format for sampling.")

        assert max_val in RASTER_HEIGHT_TRANSLATIONS, f"Raster value {max_val} not found in translation mapping."
        return RASTER_HEIGHT_TRANSLATIONS[max_val]

    def calculate(self, maximum_damage: float, damage_function: SSMFunction, base_building_data: pd.Series) -> pd.Series | None:
        flood_height = self.get_flood_height(80)
        coverage = [1]
        values = [flood_height]
        damage = get_depth_value(flood_height, damage_function) * maximum_damage
        base_building_data_dict = base_building_data.to_dict()
        base_building_data_dict["coverage"] = coverage
        base_building_data_dict["values"] = values
        base_building_data_dict["damage"] = damage
        base_building_data_dict["maximum_damage"] = maximum_damage
        return pd.Series(base_building_data_dict)