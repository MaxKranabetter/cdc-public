from src.bag.models import BAGBuildingData, PandFeature, PandQueryResponse, VerblijfsobjectQueryResponse
from src.common.models import Location, BoundingBox
import requests

from src.bag.models import LocatieServerAddress, LocatieServerResponse


geocoding_api_base_url = "https://api.pdok.nl/bzk/locatieserver/search/v3_1"

get_result_path = "/free"
suggest_result_path = "/suggest"

bag_api_base_url = "https://api.pdok.nl/kadaster/bag/ogc/v2"

bag_pand_response_path = "/collections/pand/items"
bag_verblijfsobjecten_response_path = "/collections/verblijfsobject/items"

def geocode_address(address_input: str, reference_location: Location | None = None, response_count: int = 5) -> LocatieServerResponse:
    payload = {
        "q": address_input,
        "rows": response_count,
    }
    response = _send_request(geocoding_api_base_url, get_result_path, payload)
    response_data = response.json()
    parsed_response = LocatieServerResponse.model_validate(response_data.get("response", {}))
    return parsed_response

def _get_building_polygons_from_address_object(address: LocatieServerAddress, response_limit: int, search_box_size: int = 10) -> tuple[PandQueryResponse, VerblijfsobjectQueryResponse]:
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
    pand_response = PandQueryResponse.model_validate(data)
    verblijfsobjecten_response = get_verblijfsobjecten_in_area(bbox_values)
    return pand_response, verblijfsobjecten_response

BAG_CRS = "EPSG:28992"

def get_building_polygons_from_address(address_input: str, response_limit: int, search_box_size: int = 10) -> tuple[BAGBuildingData, list[BAGBuildingData]]:
    geocode_response = geocode_address(address_input, response_count=1)
    if geocode_response.number_of_matching_addresses == 0:
        raise ValueError(f"No addresses found for input: {address_input}")
    address_object = geocode_response.docs[0]
    pand_response, verblijfsobjecten_response = _get_building_polygons_from_address_object(address_object, response_limit=response_limit, search_box_size=search_box_size)
    if pand_response.numberReturned == 0:
        raise ValueError(f"No building polygons found for address: {address_input} at {address_object.centroide_ll} with search box size {search_box_size} meters")
    building_data: list[BAGBuildingData] = []
    for feature in pand_response.features:
        building_data.append(BAGBuildingData(
            pand=feature,
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


def _send_request(base_url: str, endpoint: str, payload: dict) -> requests.Response:
    url = base_url + endpoint
    response = requests.get(url, params=payload)
    response.raise_for_status()
    return response

