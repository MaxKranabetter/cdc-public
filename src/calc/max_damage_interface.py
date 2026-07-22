from datetime import date

import pandas as pd

from src.calc.models import BuildingClass, BuildingData
from src.ssm.models import L1FunctionCategory, L2FunctionCategory, SSMFunction, SSMFunctionType
from src.cbs.cpi import get_cpi_multiplier, get_cpi_weight

# SSM max damage values from 2022:

# Structure:
# - Residential: 1295 Euro per m²

# Content:
# - Residential: 81985 Euro per Unit

# Combined:
# - Industry: 1420 Euro per m²
# - Office: 1607 Euro per m²
# - Commercial: 1796 Euro per m²

MAX_FLOOR_COUNT_FOR_DAMAGE_CALCULATION = 6

class MaxDamageInterface:

    def __init__(self, object_col: str = 'obj_type'):
        self.object_col = object_col
        self.damage_baseline_year = 2022
        self.cbs_cpi_codes_for_inflation_adjustment = {
            BuildingClass.SINGLE_UNIT_RESIDENTIAL: {
                SSMFunctionType.STRUCTURE: ["041000", "042000", "043000", "044000"],
                SSMFunctionType.CONTENT: ["050000"],
            },
            BuildingClass.MULTI_UNIT_RESIDENTIAL: {
                SSMFunctionType.STRUCTURE: ["041000", "042000", "043000", "044000"],
                SSMFunctionType.CONTENT: ["050000"],
            }
        }
        self.max_damages_per_unit = {
            BuildingClass.SINGLE_UNIT_RESIDENTIAL: {
                SSMFunctionType.STRUCTURE: 1295,
                SSMFunctionType.CONTENT: 81985,
                SSMFunctionType.COMBINED: None,
                SSMFunctionType.INVENTORY: None
            },
            BuildingClass.MULTI_UNIT_RESIDENTIAL: {
                SSMFunctionType.STRUCTURE: 1295,
                SSMFunctionType.CONTENT: 81985,
                SSMFunctionType.COMBINED: None,
                SSMFunctionType.INVENTORY: None
            },
            BuildingClass.COMMERCIAL: {
                SSMFunctionType.STRUCTURE: None,
                SSMFunctionType.CONTENT: None,
                SSMFunctionType.COMBINED: 1796,
                SSMFunctionType.INVENTORY: None
            },
            BuildingClass.OFFICE: {
                SSMFunctionType.STRUCTURE: None,
                SSMFunctionType.CONTENT: None,
                SSMFunctionType.COMBINED: 1607,
                SSMFunctionType.INVENTORY: None
            },
            BuildingClass.INDUSTRIAL: {
                SSMFunctionType.STRUCTURE: None,
                SSMFunctionType.CONTENT: None,
                SSMFunctionType.COMBINED: 1420,
                SSMFunctionType.INVENTORY: None
            }
        }

    def adjust_for_inflation(self, value: float, year_for_inflation_adjustment: int | None = None, cpi_codes: list[str] | None = None) -> float:
        year = year_for_inflation_adjustment or date.today().year - 1
        assert year >= self.damage_baseline_year, f"Year for inflation adjustment must be greater than or equal to {self.damage_baseline_year}"
        conversion_factor = 1
        if year > self.damage_baseline_year:
            try:
                if cpi_codes is None:
                    cpi_codes = ["T001112"]
                if len(cpi_codes) == 1:
                    conversion_factor = get_cpi_multiplier(self.damage_baseline_year, year)
                else:
                    # Calculate a weighted average of CPI multipliers for multiple CPI codes
                    total_weighted_multiplier = 0
                    total_weight = 0
                    for cpi_code in cpi_codes:
                        weight = get_cpi_weight(year, cpi_code)
                        if weight is not None:
                            multiplier = get_cpi_multiplier(self.damage_baseline_year, year, cpi_code)
                            total_weighted_multiplier += multiplier * weight
                            total_weight += weight
                    if total_weight > 0:
                        conversion_factor = total_weighted_multiplier / total_weight
            except ValueError as e:
                print(f"Error occurred while fetching CPI multiplier: {e}, falling back to known 2025 general inflation adjustment factor of 1.1081")
                if year != 2025:
                    print(f"Warning: Using fallback CPI multiplier for year 2022 instead of {year}, as requested.")
                    year = 2022
        return value * conversion_factor, year

    def get_unit_damage_for_building_class(self, building_class: BuildingClass, function_type: SSMFunctionType, year_for_inflation_adjustment: int | None = None) -> float:
        unit_damage = self.max_damages_per_unit.get(building_class, {}).get(function_type)
        if unit_damage is None:
            raise ValueError(f"No max damage per unit found for building class {building_class} and function type {function_type}")
        cpi_codes = self.cbs_cpi_codes_for_inflation_adjustment.get(building_class, {}).get(function_type)
        inflation_adjusted_damage, price_level = self.adjust_for_inflation(unit_damage, year_for_inflation_adjustment, cpi_codes)
        return inflation_adjusted_damage, price_level

    def get_max_damage_for_building_class(self, building_data: BuildingData, function: SSMFunction, year_for_inflation_adjustment: int | None = None) -> float:
        ground_floor_unit_damage, ground_floor_price_level = self.get_unit_damage_for_building_class(building_data.unique_ground_floor_class, function.metadata.function_type, year_for_inflation_adjustment) if building_data.unique_ground_floor_class else None
        building_footprint_area = building_data.polygon.area

        relevant_floor_count = min(MAX_FLOOR_COUNT_FOR_DAMAGE_CALCULATION, building_data.floor_count)
        if ground_floor_unit_damage is not None:
            relevant_floor_count -= 1 # ground floor is counted separately

        try:
            if ground_floor_unit_damage is not None and function.metadata.l1_category != L1FunctionCategory.RESIDENTIAL:
                # we are currently evaluating the ground floor function
                building_class = building_data.unique_ground_floor_class
            else:
                building_class = building_data.building_class
            base_unit_damage, base_price_level = self.get_unit_damage_for_building_class(building_class, function.metadata.function_type, year_for_inflation_adjustment)
        except ValueError as e:
            if function.metadata.function_type == SSMFunctionType.COMBINED and building_data.building_class in [BuildingClass.SINGLE_UNIT_RESIDENTIAL, BuildingClass.MULTI_UNIT_RESIDENTIAL]:
                structure_unit_damage, structure_price_level = self.get_unit_damage_for_building_class(building_data.building_class, SSMFunctionType.STRUCTURE, year_for_inflation_adjustment)
                content_unit_damage, content_price_level = self.get_unit_damage_for_building_class(building_data.building_class, SSMFunctionType.CONTENT, year_for_inflation_adjustment)
                structure_damage = building_footprint_area * structure_unit_damage * relevant_floor_count
                content_damage = content_unit_damage * building_data.num_units
                return structure_damage + content_damage, max(structure_price_level, content_price_level)
            else:
                raise e

        if building_data.building_class not in [BuildingClass.SINGLE_UNIT_RESIDENTIAL, BuildingClass.MULTI_UNIT_RESIDENTIAL]:
            assert ground_floor_unit_damage is None, "Non-residential buildings should not have a unique ground floor class"
            # non-residential buildings don't have unique ground floors and they also use combined damage with square metreage
            return building_footprint_area * base_unit_damage * relevant_floor_count, base_price_level
        
        if function.metadata.l1_category != L1FunctionCategory.RESIDENTIAL:
            assert ground_floor_unit_damage is not None, "Residential buildings should have a unique ground floor class for non-residential functions"
            assert function.metadata.function_type == SSMFunctionType.COMBINED, "Non-residential functions are always of type COMBINED in the current implementation"
            return building_footprint_area * ground_floor_unit_damage * 1, ground_floor_price_level # in this run we are only calculating the current function

        if function.metadata.function_type == SSMFunctionType.STRUCTURE:
            return base_unit_damage * building_footprint_area * relevant_floor_count, base_price_level
        elif function.metadata.function_type == SSMFunctionType.CONTENT:
            return base_unit_damage * building_data.num_units, base_price_level # this might slightly overcount since we might be counting ground floor units twice
        elif function.metadata.function_type == SSMFunctionType.COMBINED:
            return base_unit_damage * building_footprint_area * relevant_floor_count, base_price_level
        else:
            raise ValueError(f"Unsupported function type {function.metadata.function_type} for building class {building_data.building_class}")
    
    def get_max_damage_data(self, selected_curves: list[SSMFunction], building_data: BuildingData) -> pd.DataFrame:
        total_max_damages = []
        for curve in selected_curves:
            max_damage, price_level = self.get_max_damage_for_building_class(building_data, curve)
            total_max_damages.append((curve.metadata.id, max_damage, price_level))
        maxdam_dict = {str(curve_id): max_damage / building_data.polygon.area for curve_id, max_damage, price_level in total_max_damages} # we divide by the area here to get a per-square-metre value (considering units), which is what the DamageScanner expects
        return pd.DataFrame.from_dict(
            maxdam_dict,
            orient='index'
        ).reset_index().rename(columns={'index': self.object_col,0: 'damage'}), {str(curve_id): price_level for curve_id, max_damage, price_level in total_max_damages}
