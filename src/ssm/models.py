
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

class StoreysAboveGround(Enum):
    ZERO = "0"
    ONE = "1"
    TWO = "2"
    TWO_OR_MORE = "2+"
    THREE = "3"
    THREE_OR_MORE = "3+"
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
    storeys_above_ground: tuple[StoreysAboveGround, StoreysAboveGround] | tuple[StoreysAboveGround] | None = None
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


@dataclass
class DamageFunctionSet:
    structure_function: SSMFunction | None = None
    content_function: SSMFunction | None = None
    inventory_function: SSMFunction | None = None
    combined_function: SSMFunction | None = None

    def get_metadata(self) -> DamageFunctionSetMetadata | None:
        for func in (self.structure_function, self.content_function, self.inventory_function, self.combined_function):
            if func is not None:
                fields_to_remove = ["function_type", "id"]
                metadata_dict = {field: getattr(func.metadata, field) for field in func.metadata.__dataclass_fields__ if field not in fields_to_remove}
                return DamageFunctionSetMetadata(**metadata_dict)
        return None
    
    @property
    def functions(self) -> list[SSMFunction]:
        return [func for func in (self.structure_function, self.content_function, self.inventory_function, self.combined_function) if func is not None]

class DamageFunctionPackage:

    def __init__(self, *args):
        self.damage_function_sets = []
        if len(args) == 1 and (
            isinstance(args[0], list)
            or isinstance(args[0], tuple)
            or isinstance(args[0], dict)
        ):
            self._damage_functions = args[0].values() if isinstance(args[0], dict) else args[0]
        else:
            self._damage_functions = args
        self._damage_functions: list[SSMFunction] = list(self._damage_functions)

        if not all(isinstance(df, SSMFunction) for df in self._damage_functions):
            raise ValueError("All damage functions must be instances of SSMFunction")
        
        self.damage_function_sets: list[DamageFunctionSet] = self._match_functions()
        self.metadata = self._build_metadata()
        self.ids = [f.metadata.id for f in self._damage_functions]

    def __repr__(self):
        return f"DamageFunctionPackage(name={self.metadata.name}) with {len(self.damage_function_sets)} sets and {len(self._damage_functions)} functions"

    def _build_metadata(self) -> DamageFunctionMetadata:
        if len(self.damage_function_sets) == 0:
            raise ValueError("Cannot build metadata for package with no damage function sets.")
        sample_set_metadata = self.damage_function_sets[0].get_metadata()
        if sample_set_metadata is None:
            raise ValueError("Cannot build metadata for package with damage function sets that have no metadata.")
        fields_to_remove = ["return_period_protection", "damage_level"]
        metadata_dict = {field: getattr(sample_set_metadata, field) for field in sample_set_metadata.__dataclass_fields__ if field not in fields_to_remove}
        return DamageFunctionMetadata(**metadata_dict)

    def _does_metadata_match(self, meta1: SSMFunctionMetadata, meta2: DamageFunctionSetMetadata) -> bool:
        fields_to_match = ["name", "model", "country", "l1_category", "method", "scale", "return_period_protection", "damage_level"]
        for field in fields_to_match:
            if getattr(meta1, field) != getattr(meta2, field):
                return False
        if len(meta1.l2_categories) + len(meta2.l2_categories) > 0 and not any(cat in meta2.l2_categories for cat in meta1.l2_categories):
            return False
        if len(meta1.l3_categories) + len(meta2.l3_categories) > 0 and not any(cat in meta2.l3_categories for cat in meta1.l3_categories):
            return False
        return True
        
    def _match_functions(self) -> list[DamageFunctionSet]:
        structure_functions = [df for df in self._damage_functions if df.metadata.function_type == SSMFunctionType.STRUCTURE]
        content_functions = [df for df in self._damage_functions if df.metadata.function_type == SSMFunctionType.CONTENT]
        inventory_functions = [df for df in self._damage_functions if df.metadata.function_type == SSMFunctionType.INVENTORY]
        combined_functions = [df for df in self._damage_functions if df.metadata.function_type == SSMFunctionType.COMBINED]

        if len(combined_functions) > 0:
            if len(combined_functions) > 1:
                raise ValueError("Multiple combined damage functions found in package, but only one is allowed.")
            return [
                DamageFunctionSet(
                    combined_function=combined_functions[0]
                )
            ]

        if len(structure_functions) == 0 and len(content_functions) == 0 and len(inventory_functions) == 0:
            raise ValueError("No damage functions found in package.")
        
        if not any(len(funcs) > 1 for funcs in [structure_functions, content_functions, inventory_functions]):
            # simplest case - there are no alternations of the same function
            return [
                DamageFunctionSet(
                    structure_function=structure_functions[0] if len(structure_functions) > 0 else None,
                    content_function=content_functions[0] if len(content_functions) > 0 else None,
                    inventory_function=inventory_functions[0] if len(inventory_functions) > 0 else None,
                    combined_function=combined_functions[0] if len(combined_functions) > 0 else None,
                )
            ]
        
        # we need to group the functions such that the only difference between them is the type (structure, content, inventory) and not the metadata categories
        grouped_functions: list[DamageFunctionSet] = []

        def _place_function(func: SSMFunction, field_name: str) -> None:
            matching_groups: list[DamageFunctionSet] = []
            for group in grouped_functions:
                base_meta = group.get_metadata()
                if base_meta is not None and self._does_metadata_match(base_meta, func.metadata):
                    matching_groups.append(group)

            if len(matching_groups) > 1:
                raise ValueError(
                    f"Function {func.metadata.name} matches multiple groups, which is ambiguous."
                )

            if len(matching_groups) == 0:
                new_group = DamageFunctionSet()
                setattr(new_group, field_name, func)
                grouped_functions.append(new_group)
                return

            target_group = matching_groups[0]
            if getattr(target_group, field_name) is not None:
                raise ValueError(
                    f"Multiple {field_name.replace('_function', '')} functions found for group "
                    f"{target_group.get_metadata().name} (duplicate data)."
                )
            setattr(target_group, field_name, func)

        for func in structure_functions:
            _place_function(func, "structure_function")
        for func in content_functions:
            _place_function(func, "content_function")
        for func in inventory_functions:
            _place_function(func, "inventory_function")
        for func in combined_functions:
            _place_function(func, "combined_function")

        assert len(grouped_functions) > 0, "No grouped functions found, but there should be at least one."
        return grouped_functions