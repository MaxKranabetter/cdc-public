import logging
import random

import pandas as pd

from src.calc.models import BuildingClassifierType
from src.bag.bag_ssm_classifier import BAGSSMClassifier

from src.ssm.models import DamageFunctionPackage, IntensityUnit, SSMFunction, SSMFunctionMetadata
from src.ssm.ssm_function_loader import get_function_from_id, load_ssm_functions


class DamageFunctionInterface:

    def __init__(self):
        self.function_confidences: dict[str, DamageFunctionPackage] = {}
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
                if depth > depth_value:
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
        return {tuple(dp.ids): dp for dp in grouped_damage_functions}

    def get_damage_functions(self) -> tuple[pd.DataFrame, dict[int, DamageFunctionPackage]]:
        all_ids_with_confidence = [str(id) for ids in self.function_confidences.keys() for id in ids]
        curves_to_include = [curve for curve in self.damage_functions.values() if str(curve.metadata.id) in all_ids_with_confidence or True]
        column_headers = ["Depth"] + [str(curve.metadata.id) for curve in curves_to_include]
        depth_values = list(curves_to_include)[0].values.keys() # this assumes all curves have the same depth values, which should be the case for SSM functions - this could do with a cleaner logic that includes rescaling though
        data = []
        for depth in depth_values:
            row = [depth] + [self.get_depth_value(depth, curve) for curve in curves_to_include]
            data.append(row)
        df = pd.DataFrame(data, columns=column_headers)
        mapped_packages = {}
        for curve in curves_to_include:
            package = next((pkg for pkg in self.damage_function_packages.values() if curve.metadata.id in pkg.ids), None)
            assert package
            mapped_packages[curve.metadata.id] = package
        return df, mapped_packages
    
    def classify_bag_landuse(self, bag_data: pd.Series, max_functions: int = 5) -> list[DamageFunctionPackage]:
        functions_with_confidences = self.bag_ssm_classifier.match_functions_to_bag_object(bag_data, max_functions=max_functions)
        for func_package, confidence in functions_with_confidences:
            self.function_confidences[tuple(func_package.ids)] = confidence
        return [self.damage_function_packages[tuple(func_package.ids)] for func_package, confidence in functions_with_confidences]
    
    def get_matching_functions_for_object(self, row: pd.Series, max_functions: int = 5) -> list[DamageFunctionPackage]:
        if row["classifier_used"] == BuildingClassifierType.BAG.value:
            return self.classify_bag_landuse(row, max_functions=max_functions)
        funcs = [random.choice(list(self.damage_function_packages.values())), random.choice(list(self.damage_function_packages.values()))]
        return funcs
