import pyproj
from shapely.geometry import Point

def transform_coordinates(lng: float, lat: float, source_crs_epsg: int, target_crs_epsg: int) -> tuple[float, float]:
    transformer = pyproj.Transformer.from_crs(f"EPSG:{source_crs_epsg}", f"EPSG:{target_crs_epsg}", always_xy=True)
    transformed_lng, transformed_lat = transformer.transform(lng, lat)
    return transformed_lng, transformed_lat

def get_bounding_box(lat: float, lng: float, crs_epsg: int, length_meters: float, output_crs: int | None = None) -> tuple:
    original_crs = pyproj.CRS.from_epsg(crs_epsg)
    
    # If original is not WGS84, convert center to WGS84 for AEQD definition
    if crs_epsg != 4326:
        wgs84 = pyproj.CRS.from_epsg(4326)
        transformer_to_wgs84 = pyproj.Transformer.from_crs(original_crs, wgs84, always_xy=True)
        lon_0, lat_0 = transformer_to_wgs84.transform(lng, lat)
    else:
        lon_0, lat_0 = lng, lat

    # Define a local Azimuthal Equidistant projection centered on the specific lat/lng
    local_aeqd_proj = (
        f"+proj=aeqd +lat_0={lat_0} +lon_0={lon_0} +x_0=0 +y_0=0 "
        f"+datum=WGS84 +units=m +no_defs +type=crs"
    )
    metric_crs = pyproj.CRS.from_proj4(local_aeqd_proj)
    forward_transformer = pyproj.Transformer.from_crs(original_crs, metric_crs, always_xy=True)
    reverse_transformer = pyproj.Transformer.from_crs(metric_crs, original_crs, always_xy=True)
    
    x_metric, y_metric = forward_transformer.transform(lng, lat)
    center_point_metric = Point(x_metric, y_metric)
    
    half_side = length_meters / 2.0
    bbox_metric = center_point_metric.buffer(half_side).envelope
    minx, miny, maxx, maxy = bbox_metric.bounds
    
    corners_metric = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    
    lngs = []
    lats = []
    for cx, cy in corners_metric:
        geo_lng, geo_lat = reverse_transformer.transform(cx, cy)
        lngs.append(geo_lng)
        lats.append(geo_lat)
    
    bbox = (min(lngs), min(lats), max(lngs), max(lats))
    
    if output_crs and output_crs != crs_epsg:
        output_crs_obj = pyproj.CRS.from_epsg(output_crs)
        output_transformer = pyproj.Transformer.from_crs(original_crs, output_crs_obj, always_xy=True)
        
        corners_original = [(bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[2], bbox[3]), (bbox[0], bbox[3])]
        xs = [output_transformer.transform(x, y)[0] for x, y in corners_original]
        ys = [output_transformer.transform(x, y)[1] for x, y in corners_original]
        bbox = (min(xs), min(ys), max(xs), max(ys))
    
    return bbox
