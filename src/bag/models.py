from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.common.models import Location, SpatialFeature

class VerblijfsobjectFeatureProperties(BaseModel):
    bronhouder_identificatie: str
    bronhouder_naam: str
    documentdatum: date | None
    documentnummer: str | None
    gebruiksdoel: str | None
    geconstateerd: str | None
    hoofdadres_identificatie: str | None
    hoofdadres_status: str | None
    huisletter: str | None
    huisnummer: int | None
    identificatie: str
    openbare_ruimte_identificatie: str | None
    openbare_ruimte_naam: str | None
    openbare_ruimte_naam_kort: str | None
    openbare_ruimte_status: str | None
    oppervlakte: float | None
    pand: list[str]
    postcode: str | None
    provincie_afkorting: str | None
    provincie_naam: str | None
    status: str
    toevoeging: str | None
    woonplaats_identificatie: str | None
    woonplaats_naam: str | None
    woonplaats_status: str | None

class VerblijfsobjectFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    properties: VerblijfsobjectFeatureProperties
    geometry: SpatialFeature

    @field_validator("geometry", mode="before")
    def parse_geometry(cls, value):
        if isinstance(value, dict):
            return SpatialFeature.parse_bag_geometry(value)
        return value

class VerblijfsobjectQueryResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    timeStamp: datetime
    numberReturned: int
    features: list[VerblijfsobjectFeature]

    @field_validator("timeStamp", mode="before")
    def parse_timestamp(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

class PandFeatureProperties(BaseModel):
    aantal_verblijfsobjecten: int
    bouwjaar: int | None
    documentdatum: date | None
    documentnummer: str | None
    gebruiksdoel: str | None
    geconstateerd: str | None
    identificatie: str
    rdf_seealso: str | None
    status: str
    verblijfsobject_href: list[str] = []

    @field_validator("documentdatum", mode="before")
    def parse_documentdatum(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        return value

class PandFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    properties: PandFeatureProperties
    geometry: SpatialFeature

    @field_validator("geometry", mode="before")
    def parse_geometry(cls, value):
        if isinstance(value, dict):
            return SpatialFeature.parse_bag_geometry(value)
        return value

class PandQueryResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    timeStamp: datetime
    responseLimit: int
    numberReturned: int
    links: list
    features: list[PandFeature]

    @field_validator("timeStamp", mode="before")
    def parse_timestamp(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
    
class BAGBuildingData(BaseModel):
    pand: PandFeature
    verblijfsobjecten: list[VerblijfsobjectFeature]

class LocatieServerAddress(BaseModel):
    bron: str | None = None
    woonplaatscode: str | None = None
    type: str | None = None
    woonplaatsnaam: str | None = None
    wijkcode: str | None = None
    huis_nlt: str | None = None
    openbareruimtetype: str | None = None
    buurtnaam: str | None = None
    gemeentecode: str | None = None
    rdf_seealso: str | None = None
    weergavenaam: str | None = None
    straatnaam_verkort: str | None = None
    id: str | None = None
    gekoppeld_perceel: list[str] | None = None
    gemeentenaam: str | None = None
    buurtcode: str | None = None
    wijknaam: str | None = None
    identificatie: str | None = None
    openbareruimte_id: str | None = None
    waterschapsnaam: str | None = None
    provinciecode: str | None = None
    postcode: str | None = None
    provincienaam: str | None = None
    centroide_ll: Location | None = None
    nummeraanduiding_id: str | None = None
    waterschapscode: str | None = None
    adresseerbaarobject_id: str | None = None
    huisnummer: int | str | None = None
    provincieafkorting: str | None = None
    centroide_rd: Location | None = None
    straatnaam: str | None = None
    gekoppeld_appartement: list[str] | None = None
    score: float | None = None

    @field_validator("centroide_rd", mode="before")
    def parse_centroide_rd(cls, value):
        if not isinstance(value, str):
            return None
        if value.startswith("POINT"):
            coords = value[6:-1].split()
            return Location(lat=float(coords[1]), lon=float(coords[0]), crs="EPSG:28992")
        return None
    
    @field_validator("centroide_ll", mode="before")
    def parse_centroide_ll(cls, value):
        if not isinstance(value, str):
            return None
        if value.startswith("POINT"):
            coords = value[6:-1].split()
            return Location(lat=float(coords[1]), lon=float(coords[0]), crs="EPSG:4326")
        return None

class LocatieServerResponse(BaseModel):
    number_of_matching_addresses: int = Field(..., alias='numFound')
    start: int
    max_score: float = Field(..., alias='maxScore')
    num_found_exact: bool = Field(..., alias='numFoundExact')
    docs: list[LocatieServerAddress]