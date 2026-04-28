import pandas as pd

from src.ssm.models import L1FunctionCategory, SSMFunction, SSMFunctionType


class MaxDamageInterface:

    def __init__(self, object_col: str = 'obj_type'):
        self.object_col = object_col
        self.max_damages_per_sqm = {
            L1FunctionCategory.EMPLOYMENT: {
                SSMFunctionType.STRUCTURE: 580.5,
                SSMFunctionType.CONTENT: 580.5,
                SSMFunctionType.COMBINED: 1161,
                SSMFunctionType.INVENTORY: 580.5 # placeholder
            },
            L1FunctionCategory.RESIDENTIAL: {
                SSMFunctionType.STRUCTURE: 561,
                SSMFunctionType.CONTENT: 281,
                SSMFunctionType.COMBINED: 842
            },
            L1FunctionCategory.MULTIPLE: {
                SSMFunctionType.STRUCTURE: 0, # placeholder
                SSMFunctionType.CONTENT: 0, # TODO: implement
                SSMFunctionType.COMBINED: 0
            },
            L1FunctionCategory.INFRASTRUCTURE: {
                SSMFunctionType.STRUCTURE: 0, # placeholder
                SSMFunctionType.CONTENT: 0, # TODO: implement
                SSMFunctionType.COMBINED: 0
            },
            L1FunctionCategory.OTHER: {
                SSMFunctionType.STRUCTURE: 0, # placeholder
                SSMFunctionType.CONTENT: 0, # TODO: implement
                SSMFunctionType.COMBINED: 0
            }
        }

    def get_max_damage_per_sqm_for_function(self, function: SSMFunction) -> float:
        # TODO: logic needs to be refined
        damage = self.max_damages_per_sqm.get(function.metadata.l1_category, {}).get(function.metadata.function_type)
        if damage is None:
            raise ValueError(f"No max damage per sqm found for function with L1 category {function.metadata.l1_category} and function type {function.metadata.function_type}")
        return damage
    
    def get_max_damage_data(self, selected_curves: list[SSMFunction]) -> pd.DataFrame:
        maxdam_dict = {str(curve.metadata.id): self.get_max_damage_per_sqm_for_function(curve) for curve in selected_curves}
        return pd.DataFrame.from_dict(maxdam_dict, orient='index').reset_index().rename(columns={'index': self.object_col, 0: 'damage'})
