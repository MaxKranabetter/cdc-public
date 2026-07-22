import logging

import pandas as pd
from src.calc.models import BuildingClass, BuildingData
from src.bag.bag_ssm_classifier import BAGSSMClassifier

from src.ssm.models import DamageFunctionPackage, IntensityUnit, SSMFunction, SSMFunctionMetadata
from src.ssm.ssm_function_loader import get_function_from_id, load_ssm_functions


class DamageFunctionInterface:

    def __init__(self):
        self.damage_function_metadata: dict[int, SSMFunctionMetadata] = load_ssm_functions()
        self.filter_damage_functions()
        self.damage_function_packages = self.group_damage_functions()
        self.bag_ssm_classifier = BAGSSMClassifier(self.damage_function_packages)

    def get_depth_value(self, depth: float, function: SSMFunction) -> float:
        if depth in function.values:
            return function.values[depth]
        else:
            # interpolate value
            sorted_depths = sorted(function.values.keys())
            for index, depth_value in enumerate(sorted_depths):
                if depth_value > depth:
                    if index == 0:
                        return function.values[depth_value]
                    else:
                        lower_value = function.values[sorted_depths[index-1]]
                        upper_value = function.values[depth_value]
                        # linear interpolation
                        depth_diff = depth_value - sorted_depths[index-1]
                        value_diff = upper_value - lower_value
                        percent_diff = (depth - sorted_depths[index-1]) / depth_diff
                        if depth_diff == 0:
                            return lower_value
                        else:
                            return lower_value + (percent_diff * value_diff)
        return float('nan')

    def filter_damage_functions(self) -> dict[str, SSMFunction]:
        useable_curves: list[SSMFunction] = []
        for metadata in self.damage_function_metadata.values():
            curve = get_function_from_id(metadata.id)
            if curve is None:
                logging.warning(f"Could not load curve with ID {metadata.id} and name {metadata.name}")
                continue
            if curve.intensity_unit != IntensityUnit.DEPTH_METERS:
                logging.warning(f"Skipping curve {curve.metadata.name} with unsupported intensity unit {curve.intensity_unit}")
                continue
            useable_curves.append(curve)
        if len(useable_curves) == 0:
            raise ValueError("No useable curves found with intensity unit in depth meters.")
        self.damage_functions = {str(curve.metadata.id): curve for curve in useable_curves}
        return self.damage_functions
    
    def _do_functions_match(self, func1: SSMFunction, func2: SSMFunction) -> bool:
        if func1.metadata.name == func2.metadata.name:

            if func1.metadata.model != func2.metadata.model:
                logging.warning(f"Matching functions {func1.metadata.name} have different damage models: {func1.metadata.model} vs {func2.metadata.model}")
                return False
            if func1.metadata.country != func2.metadata.country:
                logging.warning(f"Matching functions {func1.metadata.name} have different countries: {func1.metadata.country} vs {func2.metadata.country}")
                return False
            
            if func1.metadata.l1_category != func2.metadata.l1_category:
                logging.warning(f"Matching functions {func1.metadata.name} have different L1 categories: {func1.metadata.l1_category} vs {func2.metadata.l1_category}")
                return False
            if len(func1.metadata.l2_categories) + len(func2.metadata.l2_categories) > 0 and not any(cat in func2.metadata.l2_categories for cat in func1.metadata.l2_categories):
                logging.warning(f"Matching functions {func1.metadata.name} have different L2 categories: {func1.metadata.l2_categories} vs {func2.metadata.l2_categories}")
                return False
            if len(func1.metadata.l3_categories) + len(func2.metadata.l3_categories) > 0 and not any(cat in func2.metadata.l3_categories for cat in func1.metadata.l3_categories):
                logging.warning(f"Matching functions {func1.metadata.name} have different L3 categories: {func1.metadata.l3_categories} vs {func2.metadata.l3_categories}")
                return False
            
            return True
        
        return False
    
    def group_damage_functions(self) -> dict[tuple[int], DamageFunctionPackage]:
        grouped_damage_functions: list[DamageFunctionPackage] = []
        grouped_functions: list[SSMFunction] = []
        all_funcs = list(self.damage_functions.values())
        for i in range(0, len(self.damage_functions)):
            current_function = all_funcs[i]
            if current_function in grouped_functions:
                continue
            current_group = [current_function]
            for j in range(i+1, len(self.damage_functions)):
                if self._do_functions_match(current_function, all_funcs[j]):
                    current_group.append(all_funcs[j])
            grouped_damage_functions.append(DamageFunctionPackage(current_group))
            grouped_functions.extend(current_group)
        return {id_: dp for dp in grouped_damage_functions for id_ in dp.ids}

    def get_damage_functions(self, building_data: BuildingData) -> tuple[pd.DataFrame, dict[int, DamageFunctionPackage]]:
        packages_to_include: set[DamageFunctionPackage] = set()
        main_function, secondary_function = self.get_matching_functions_for_object(building_data)
        if main_function is not None:
            packages_to_include.add(main_function)
        if secondary_function is not None:
            packages_to_include.add(secondary_function)
        column_headers = ["Depth"] + [str(id) for pkg in packages_to_include for id in pkg.ids]
        data = []
        all_curves = [curve for set_ in [set_ for pkg in packages_to_include for set_ in pkg.damage_function_sets] for curve in set_.functions]
        for depth in range(0, 18000, 10): # 0 to 18 meters in 1 cm increments
            depth /= 1000.0 # convert to meters
            row = [depth] + [self.get_depth_value(depth, curve) for curve in all_curves]
            data.append(row)
        df = pd.DataFrame(data, columns=column_headers)
        df.set_index("Depth", inplace=True)
        df.fillna(1, inplace=True) # if the function has no value, assume maximum damage
        mapped_packages = {}
        for curve in all_curves:
            package = next((pkg for pkg in self.damage_function_packages.values() if curve.metadata.id in pkg.ids), None)
            assert package
            mapped_packages[curve.metadata.id] = package
        return df, mapped_packages
    
    def _get_function_for_sbi_code(self, sbi_code: str) -> DamageFunctionPackage | None:
        # TODO: implement
        return None
    
    def _get_matching_function_for_class(self, building_class: BuildingClass, sbi_code: str | None) -> DamageFunctionPackage | None:
        match building_class:
            case BuildingClass.SINGLE_UNIT_RESIDENTIAL:
                return self.damage_function_packages[7]
            case BuildingClass.MULTI_UNIT_RESIDENTIAL:
                return self.damage_function_packages[9] # TODO: make sure this is grouped with 395 and 396
            case BuildingClass.INDUSTRIAL:
                return self._get_function_for_sbi_code(sbi_code) # or generic industrial function
            case BuildingClass.COMMERCIAL:
                return self.damage_function_packages[391]
            case BuildingClass.OFFICE:
                return self.damage_function_packages[392]
            case BuildingClass.OTHER:
                return None

    def get_matching_functions_for_object(self, building: BuildingData) -> tuple[DamageFunctionPackage, DamageFunctionPackage | None]:
        main_function = self._get_matching_function_for_class(building.building_class, building.sbi_code)
        secondary_function = None
        if building.unique_ground_floor_class is not None:
            secondary_function = self._get_matching_function_for_class(building.unique_ground_floor_class, building.sbi_code)
        return main_function, secondary_function

    def generate_description_for_function_id(self, function_id: int) -> str:
        return "Placeholder description text"