
from dataclasses import dataclass
from enum import Enum


class DamageModel(Enum):
    HIS_SSM = "HIS-SSM"
    Rhine_Atlas = "Rhine Atlas"
    _1953 = "1953"
    BILLAHAR = "Billah"
    CUSTOM = "Custom"
    FIAT = "FIAT"
    FLEMOCS = "FLEMOcs"
    FLEMOPS = "FLEMOps"
    HAZUS_MH = "HAZUS-MH"
    MCM = "MCM"
    TEBODIN = "Tebodin"

class Country(Enum):
    NLD = "Netherlands"
    DEU = "Germany"
    GBR = "United Kingdom"
    USA = "United States"
    MULTIPLE = "Multiple"

class SSMFunctionType(Enum):
    COMBINED = "Combined"
    STRUCTURE = "Structure"
    CONTENT = "Content"
    INVENTORY = "Inventory"

class DamageLevel(Enum):
    LOW = "Low"
    AVERAGE = "Average"
    HIGH = "High"

class L1FunctionCategory(Enum):
    RESIDENTIAL = "Residential"
    EMPLOYMENT = "Employment"
    INFRASTRUCTURE = "Infrastructure"
    MULTIPLE = "Multiple"
    OTHER = "Other"

class L2FunctionCategory(Enum):
    AGRICULTURE = "Agriculture"
    APARTMENTS = "Apartments"
    COMMERCIAL = "Commercial"
    EDUCATION = "Education"
    GENERIC = "Generic"
    HOSPITAL = "Hospital"
    INDUSTRIAL = "Industrial"
    OFFICE = "Office"
    SINGLE_FAMILY = "Single-family"
    TRANSPORTATION = "Transportation"
    VEHICLE = "Vehicle"
    WATER = "Water"
    OTHER = "Other"

class L3FunctionCategory(Enum):
    BANK = "Bank"
    TERRACED = "Terraced"
    SEMI_DETACHED = "Semi-detached"
    FULLY_DETACHED = "Fully-detached"
    HORECA = "Horeca"
    LIBRARY = "Library"
    SCHOOL = "School"
    SOCIAL_INFRASTRUCTURE = "Social Infrastructure"
    SPORTS_AND_RECREATION = "Sports & Recreation"
    WAREHOUSE = "Warehouse"
    OTHER = "Other"

CATEGORY_FLOW = {
    L1FunctionCategory.RESIDENTIAL: {
        L2FunctionCategory.APARTMENTS: [],
        L2FunctionCategory.SINGLE_FAMILY: [
            L3FunctionCategory.TERRACED,
            L3FunctionCategory.SEMI_DETACHED,
            L3FunctionCategory.FULLY_DETACHED
        ],
    },
    L1FunctionCategory.EMPLOYMENT: {
        L2FunctionCategory.AGRICULTURE: [],
        L2FunctionCategory.COMMERCIAL: [
            L3FunctionCategory.BANK,
            L3FunctionCategory.HORECA,
            L3FunctionCategory.SPORTS_AND_RECREATION
        ],
        L2FunctionCategory.EDUCATION: [
            L3FunctionCategory.LIBRARY,
            L3FunctionCategory.SCHOOL,
        ],
        L2FunctionCategory.HOSPITAL: [],
        L2FunctionCategory.INDUSTRIAL: [
            L3FunctionCategory.WAREHOUSE
        ],
        L2FunctionCategory.OFFICE: [
            L3FunctionCategory.SOCIAL_INFRASTRUCTURE
        ],
    },
    L1FunctionCategory.INFRASTRUCTURE: {
        L2FunctionCategory.TRANSPORTATION: [],
        L2FunctionCategory.WATER: []
    }
}

class SSMFunctionMethod(Enum):
    COMBINATION = "Combination"
    OBSERVATIONS = "Observations"
    EXPERT_CALCULATION = "Expert calculation"

class SSMFunctionScale(Enum):
    MICRO = "Micro"
    MESO = "Meso"
    NA = "NA"

@dataclass
class DamageFunctionMetadata:
    name: str
    model: DamageModel
    country: Country
    l1_category: L1FunctionCategory
    l2_categories: list[L2FunctionCategory]
    l3_categories: list[L3FunctionCategory]
    method: SSMFunctionMethod
    scale: SSMFunctionScale
    notes: str | None = None
    source_description: str | None = None

@dataclass(kw_only=True)
class DamageFunctionSetMetadata(DamageFunctionMetadata):
    return_period_protection: int = 0
    damage_level: DamageLevel = DamageLevel.AVERAGE

@dataclass(kw_only=True)
class SSMFunctionMetadata(DamageFunctionSetMetadata):
    id: int
    function_type: SSMFunctionType

class IntensityUnit(Enum):
    DEPTH_METERS = "Depth (m)"
    VELOCITY_METERS_SECOND = "Velocity (m/s)"
    OTHER = "Other"

@dataclass
class SSMFunction:
    metadata: SSMFunctionMetadata
    values: dict[float, float]  # mapping from hazard intensity (flood depth) to damage ratio
    intensity_unit: IntensityUnit