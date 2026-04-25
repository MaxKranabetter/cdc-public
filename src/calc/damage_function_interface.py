import logging
import random

import pandas as pd

from src.calc.models import BuildingClassifierType
from src.bag.bag_ssm_classifier import BAGSSMClassifier

from src.ssm.models import IntensityUnit, SSMFunction, SSMFunctionMetadata
from src.ssm.ssm_function_loader import get_function_from_id, load_ssm_functions

class DamageFunctionInterface:

    def __init__(self):
        self.function_confidences = {}
        self.damage_function_metadata: dict[int, SSMFunctionMetadata] = load_ssm_functions()
        self.filter_damage_functions()
        self.bag_ssm_classifier = BAGSSMClassifier(self.damage_function_metadata)

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

    def get_damage_functions(self) -> pd.DataFrame:
        curves_to_include = [curve for curve in self.damage_functions.values() if str(curve.metadata.id) in self.function_confidences]
        column_headers = ["Depth"] + [str(curve.metadata.id) for curve in curves_to_include]
        depth_values = list(curves_to_include)[0].values.keys() # this assumes all curves have the same depth values, which should be the case for SSM functions - this could do with a cleaner logic that includes rescaling though
        data = []
        for depth in depth_values:
            row = [depth] + [self.get_depth_value(depth, curve) for curve in curves_to_include]
            data.append(row)
        return pd.DataFrame(data, columns=column_headers)
    
    def classify_bag_landuse(self, bag_data: pd.Series) -> list[SSMFunction]:
        functions_with_confidences = self.bag_ssm_classifier.match_functions_to_bag_object(bag_data, max_functions=5)
        for func_meta, confidence in functions_with_confidences:
            self.function_confidences[str(func_meta.id)] = confidence
        return [self.damage_functions[str(func_meta.id)] for func_meta, confidence in functions_with_confidences]
    
    def get_matching_functions_for_object(self, row: pd.Series) -> list[SSMFunction]:
        if row["classifier_used"] == BuildingClassifierType.BAG.value:
            return self.classify_bag_landuse(row)
        funcs = [random.choice(list(self.damage_functions.values())), random.choice(list(self.damage_functions.values()))]
        for func in funcs:
            self.function_confidences[str(func.metadata.id)] = 0
        return funcs
