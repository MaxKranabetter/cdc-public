from enum import Enum

from pydantic import BaseModel, model_validator
from src.common.spatial_utils import get_bounding_box, transform_coordinates
from geopy.distance import geodesic
from shapely.geometry import Point, Polygon

class Location(BaseModel):
    lat: float
    lon: float
    crs: str

    def distance(self, other: 'Location') -> float:
        """Calculate distance between two locations, accounting for CRS differences."""
        
        if self.crs != other.crs:
            other_converted = other.to_crs(self.crs)
        else:
            other_converted = other
        
        # Check if CRS uses meters (projected) or degrees (geographic)
        if self.crs.startswith("EPSG:4") or "WGS84" in self.crs:
            # Geographic CRS (degrees) - use geodesic
            return geodesic((self.lat, self.lon), (other_converted.lat, other_converted.lon)).meters
        else:
            # Projected CRS (meters) - use Euclidean distance
            return ((self.lat - other_converted.lat)**2 + (self.lon - other_converted.lon)**2)**0.5
    
    def to_crs(self, target_crs: str) -> 'Location':
        """Convert location to a different CRS."""
        
        source_epsg = int(self.crs.split(":")[1])
        target_epsg = int(target_crs.split(":")[1])
        
        new_lon, new_lat = transform_coordinates(
            lng=self.lon,
            lat=self.lat,
            source_crs_epsg=source_epsg,
            target_crs_epsg=target_epsg
        )
        
        return Location(lat=new_lat, lon=new_lon, crs=target_crs)

class BoundingBox(BaseModel):
    top_left: Location
    bottom_right: Location
    crs: str

    @classmethod
    def from_point(cls, location: Location, size_meters: int, desired_crs: str | None = None) -> 'BoundingBox':
        min_lng, min_lat, max_lng, max_lat = get_bounding_box(
            lat=location.lat,
            lng=location.lon,
            crs_epsg=int(location.crs.split(":")[1]),
            length_meters=size_meters,
            output_crs=desired_crs
        )
        return cls(
            top_left=Location(lat=max_lat, lon=min_lng, crs=location.crs),
            bottom_right=Location(lat=min_lat, lon=max_lng, crs=location.crs),
            crs=location.crs
        )

    @model_validator(mode="before")
    def validate_coordinates(cls, values):
        top_left = values.get('top_left')
        bottom_right = values.get('bottom_right')

        if top_left and bottom_right:
            if top_left.lat < bottom_right.lat:
                raise ValueError("Top left latitude must be greater than bottom right latitude.")
            if top_left.lon > bottom_right.lon:
                raise ValueError("Top left longitude must be less than bottom right longitude.")
        
        if len(list(set([top_left.crs, bottom_right.crs]))) > 1:
            raise ValueError("CRS of top left and bottom right must be the same.")

        return values

    @property
    def top_right(self) -> Location:
        return Location(lat=self.top_left.lat, lon=self.bottom_right.lon, crs=self.top_left.crs)
    
    @property
    def bottom_left(self) -> Location:
        return Location(lat=self.bottom_right.lat, lon=self.top_left.lon, crs=self.top_left.crs)
    
    @property
    def center(self) -> Location:
        return Location(
            lat=(self.top_left.lat + self.bottom_right.lat) / 2,
            lon=(self.top_left.lon + self.bottom_right.lon) / 2,
            crs=self.top_left.crs
        )
    
    @property
    def width(self) -> float:
        return self.top_right.lon - self.top_left.lon
    
    @property
    def height(self) -> float:
        return self.top_left.lat - self.bottom_right.lat
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
class FeatureType(Enum):
    POLYGON = "Polygon"
    POINT = "Point"
    
class SpatialFeature(BaseModel):
    type: FeatureType
    coordinates: list

    def get_centroid(self, coordinate_crs: str) -> Location:
        raise NotImplementedError("get_centroid must be implemented by subclasses")
    
    def to_shapely(self):
        raise NotImplementedError("to_shapely must be implemented by subclasses")
    
    @classmethod
    def parse_bag_geometry(cls, geometry: dict) -> 'SpatialFeature':
        feature_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        
        if feature_type == "Polygon":
            return PolygonFeature(type=FeatureType.POLYGON, coordinates=coordinates)
        elif feature_type == "Point":
            return PointFeature(type=FeatureType.POINT, coordinates=tuple(coordinates))
        else:
            raise ValueError(f"Unsupported geometry type: {feature_type}")
    
class PolygonFeature(SpatialFeature):
    type: FeatureType = FeatureType.POLYGON
    coordinates: list[list[tuple[float, float]]]

    def get_centroid(self, coordinate_crs: str) -> Location:
        all_coords = [coord for part in self.coordinates for coord in part]
        avg_lat = sum(coord[1] for coord in all_coords) / len(all_coords)
        avg_lon = sum(coord[0] for coord in all_coords) / len(all_coords)
        return Location(lat=avg_lat, lon=avg_lon, crs=coordinate_crs)
    
    def to_shapely(self):
        return [Polygon(part) for part in self.coordinates]
    
class PointFeature(SpatialFeature):
    type: FeatureType = FeatureType.POINT
    coordinates: tuple[float, float]

    def get_centroid(self, coordinate_crs: str) -> Location:
        return Location(lat=self.coordinates[1], lon=self.coordinates[0], crs=coordinate_crs)
    
    def to_shapely(self):
        return [Point(self.coordinates)]