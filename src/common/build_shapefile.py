import geopandas as gpd
from shapely.geometry import Polygon
import os
import tempfile

def create_gdf(coords: list[list[tuple[float, float]]] | list[tuple[float, float]], attributes: list[dict] | dict, crs="EPSG:4326") -> gpd.GeoDataFrame:
    if isinstance(coords[0], tuple):
        coords = [coords]
    data = []
    for polygon_feature in coords:
        polygon = Polygon(polygon_feature)
        row_data = attributes.pop(0) if isinstance(attributes, list) else attributes.copy()
        row_data['geometry'] = polygon
        data.append(row_data)
    gdf = gpd.GeoDataFrame(data, crs=crs)
    return gdf

def create_polygon_shapefile(
    coords: list[list[tuple[float, float]]] | list[tuple[float, float]],
    attributes: list[dict] | dict,
    output_filepath: str | None = None,
    crs="EPSG:4326",
    temporary: bool = False,
) -> str:

    if temporary:
        temp_dir = tempfile.mkdtemp(prefix="polygon_shapefile_")
        output_filepath = os.path.join(temp_dir, "polygon.shp")
    elif not output_filepath:
        raise ValueError("output_filepath is required when temporary=False")

    gdf = create_gdf(coords, attributes, crs)
    gdf.to_file(output_filepath, driver="ESRI Shapefile")
    return output_filepath
