from dataclasses import dataclass
import logging
import random

import pandas as pd

from src.calc.models import BuildingClassifierType
from src.bag.bag_ssm_classifier import BAGSSMClassifier

from src.ssm.models import DamageFunctionMetadata, DamageFunctionSetMetadata, IntensityUnit, SSMFunction, SSMFunctionMetadata, SSMFunctionType
from src.ssm.ssm_function_loader import get_function_from_id, load_ssm_functions

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
    
    def group_damage_functions(self) -> list[DamageFunctionPackage]:
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
        return grouped_damage_functions

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
