from src.bag.models import BAGBuildingData, PandFeature, PandQueryResponse, VerblijfsobjectQueryResponse
from src.common.models import Location, BoundingBox
import numpy as np
import rasterio
import requests

from src.bag.models import LocatieServerAddress, LocatieServerResponse


geocoding_api_base_url = "https://api.pdok.nl/bzk/locatieserver/search/v3_1"

get_result_path = "/free"
suggest_result_path = "/suggest"

bag_api_base_url = "https://api.pdok.nl/kadaster/bag/ogc/v2"

bag_pand_response_path = "/collections/pand/items"
bag_verblijfsobjecten_response_path = "/collections/verblijfsobject/items"


class AddressOutOfCoverageError(ValueError):
    """Raised when a geocoded address falls outside floodmap coverage."""

def geocode_address(address_input: str, reference_location: Location | None = None, response_count: int = 5) -> LocatieServerResponse:
    payload = {
        "q": address_input,
        "rows": response_count,
    }
    response = _send_request(geocoding_api_base_url, get_result_path, payload)
    response_data = response.json()
    parsed_response = LocatieServerResponse.model_validate(response_data.get("response", {}))
    return parsed_response


def _is_out_of_coverage_raster_value(value: float, nodata: float | int | None) -> bool:
    if np.isnan(value):
        return True
    if nodata is None:
        return False
    if isinstance(nodata, float) and np.isnan(nodata):
        return np.isnan(value)
    return bool(np.isclose(value, float(nodata)))


def validate_address_within_floodmap_coverage(address: LocatieServerAddress, floodmap_path: str, buffer_m: int = 10) -> None:
    centroid = address.centroide_rd or address.centroide_ll
    if centroid is None:
        raise ValueError("Unable to validate floodmap coverage: geocoded address has no centroid.")

    with rasterio.open(floodmap_path) as src:
        if src.crs is None:
            raise ValueError(f"Floodmap '{floodmap_path}' has no CRS defined.")

        raster_crs = src.crs.to_string()
        raster_location = centroid.to_crs(raster_crs) if centroid.crs != raster_crs else centroid
        x = raster_location.lon
        y = raster_location.lat

        is_inside_bounds = (
            src.bounds.left <= x <= src.bounds.right
            and src.bounds.bottom <= y <= src.bounds.top
        )
        if not is_inside_bounds:
            raise AddressOutOfCoverageError(
                "The address is outside the available flood-depth data coverage. Please choose an address inside the modeled area (City of Amsterdam)."
            )

        buf_left = src.bounds.left - buffer_m
        buf_right = src.bounds.right + buffer_m
        buf_bottom = src.bounds.bottom - buffer_m
        buf_top = src.bounds.top + buffer_m

        # sample random points within the buffered bounds to check for coverage
        sample_points_within_buffer = [
            (np.random.uniform(buf_left, buf_right),
             np.random.uniform(buf_bottom, buf_top))
            for _ in range(1 + buffer_m**2 // 50)
        ]

        sampled_values = [float(next(src.sample([(x_sample, y_sample)]))[0]) for x_sample, y_sample in sample_points_within_buffer]
        if all(_is_out_of_coverage_raster_value(value, src.nodata) for value in sampled_values):
            raise AddressOutOfCoverageError(
                "The address is outside the available flood-depth data coverage. Please choose an address inside the modeled area (City of Amsterdam)."
            )

def _get_building_polygons_from_address_object(address: LocatieServerAddress, response_limit: int, search_box_size: int = 10) -> PandQueryResponse:
    endpoint = bag_pand_response_path
    bbox = BoundingBox.from_point(address.centroide_ll or address.centroide_rd, size_meters=search_box_size, desired_crs=4326)
    bbox_values = ','.join([str(bbox.bottom_left.lon), str(bbox.bottom_left.lat), str(bbox.top_right.lon), str(bbox.top_right.lat)])
    
    response = _send_request(bag_api_base_url, endpoint, {
        'bbox': bbox_values,
        'bbox-crs': "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        'crs': "http://www.opengis.net/def/crs/EPSG/0/28992", # RD New
        'f': 'json',
        'profile': 'rel-as-key',
        'limit': response_limit
    })
    data = response.json()
    data["responseLimit"] = response_limit
    return PandQueryResponse.model_validate(data)

BAG_CRS = "EPSG:28992"

def get_building_polygons_from_address(address_input: str, response_limit: int, search_box_size: int = 10, coverage_floodmap_path: str | None = None, is_overlast: bool = False) -> tuple[BAGBuildingData, list[BAGBuildingData]]:
    geocode_response = geocode_address(address_input, response_count=1)
    if geocode_response.number_of_matching_addresses == 0:
        raise ValueError(f"No addresses found for input: {address_input}")
        
    address_object = geocode_response.docs[0]
    
    if coverage_floodmap_path is not None:
        validate_address_within_floodmap_coverage(address_object, coverage_floodmap_path, buffer_m=50 if is_overlast else 10)
        
    # Now only fetches the building(s)
    pand_response = _get_building_polygons_from_address_object(address_object, response_limit=response_limit, search_box_size=search_box_size)
    
    if pand_response.numberReturned == 0:
        raise ValueError(f"No building polygons found for address: {address_input} at {address_object.centroide_ll} with search box size {search_box_size} meters")
        
    building_data: list[BAGBuildingData] = []
    for feature in pand_response.features:
        # Fetch verblijfsobjecten using the building's exact bounding box
        verblijfsobjecten_response = get_verblijfsobjecten_for_pand(feature)
        
        building_data.append(BAGBuildingData(
            pand=feature,
            # Re-add the local filter to drop any neighboring units caught in the spatial box
            verblijfsobjecten=[v for v in verblijfsobjecten_response.features if feature.id in v.properties.pand]
        ))

    # find feature that is closest to the geocoded address centroid
    address_centroid = address_object.centroide_rd or address_object.centroide_ll
    address_location = Location(lat=address_centroid.lat, lon=address_centroid.lon, crs=address_centroid.crs)
    closest_feature = min(building_data, key=lambda f: f.pand.geometry.get_centroid(coordinate_crs=BAG_CRS).distance(address_location))
    
    return closest_feature, [feature for feature in building_data if feature != closest_feature]

def get_verblijfsobjecten_in_area(bbox_str: str) -> VerblijfsobjectQueryResponse:
    endpoint = bag_verblijfsobjecten_response_path
    response = _send_request(bag_api_base_url, endpoint, {
        'bbox': bbox_str,
        'bbox-crs': "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        'crs': "http://www.opengis.net/def/crs/EPSG/0/28992", # RD New
        'f': 'json',
        'profile': 'rel-as-key',
    })
    data = response.json()
    return VerblijfsobjectQueryResponse.model_validate(data)

def get_verblijfsobjecten_for_pand(pand_feature: PandFeature) -> VerblijfsobjectQueryResponse:
    minx, miny, maxx, maxy = pand_feature.geometry.get_bounding_box()
    
    # Add a 2-meter buffer to the building's bounding box just to be safe
    bbox_str = f"{minx - 2},{miny - 2},{maxx + 2},{maxy + 2}"
    
    endpoint = bag_verblijfsobjecten_response_path
    response = _send_request(bag_api_base_url, endpoint, {
        'bbox': bbox_str,
        'bbox-crs': "http://www.opengis.net/def/crs/EPSG/0/28992", 
        'crs': "http://www.opengis.net/def/crs/EPSG/0/28992",
        'f': 'json',
        'profile': 'rel-as-key',
        'limit': 1000 # Max limit to ensure we fetch all units
    })
    
    data = response.json()
    return VerblijfsobjectQueryResponse.model_validate(data)

def get_3d_bag_data_for_pand(pand_id: str) -> dict:
    bag3d_api_base_url = "https://api.3dbag.nl/"
    endpoint = f"collections/pand/items/NL.IMBAG.Pand.{pand_id}"
    response = _send_request(bag3d_api_base_url, endpoint, {})
    return response.json()

def _send_request(base_url: str, endpoint: str, payload: dict) -> requests.Response:
    url = base_url + endpoint
    response = requests.get(url, params=payload)
    response.raise_for_status()
    return response