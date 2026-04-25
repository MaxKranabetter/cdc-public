from enum import Enum
import logging
from pathlib import Path

import pandas as pd

from src.ssm.models import Country, DamageLevel, DamageModel, IntensityUnit, L1FunctionCategory, L3FunctionCategory, L2FunctionCategory, SSMFunction, SSMFunctionMetadata, SSMFunctionMethod, SSMFunctionScale, SSMFunctionType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SSM_FUNCTIONS_PATH = PROJECT_ROOT / "data" / "ssm" / "functies"
FUNCTION_MAP_FILE_NAME = PROJECT_ROOT / "data" / "ssm" / "function_mapping.csv"


def _load_ssm_function_mapping() -> pd.DataFrame:
    df = pd.read_csv(FUNCTION_MAP_FILE_NAME, delimiter=",", encoding="utf-8")
    df["Subcategory"] = df["Subcategory"].fillna("")
    df["Secondary Subcategory"] = df["Secondary Subcategory"].fillna("")
    return df

def _parse_function_metadata(row: pd.Series) -> SSMFunctionMetadata:

    def _parse_enum(enum_class: Enum, value: str) -> Enum | None:
        try:
            return enum_class(value)
        except ValueError:
            try:
                return next(e for e in enum_class if e.value == value)
            except StopIteration:
                logging.warning(ValueError(f"Unknown value for {enum_class.__name__}: {value}"))
                return None
                
    parsed_l2_cats = [(cat, _parse_enum(L2FunctionCategory, cat.strip())) for cat in row["Subcategory"].split(";") if cat != ""]
    unparsed_l2_cats = [cat for cat, parsed in parsed_l2_cats if parsed is None]
    parsed_l3_cats = [(cat, _parse_enum(L3FunctionCategory, cat.strip())) for cat in row["Secondary Subcategory"].split(";") + unparsed_l2_cats if cat != ""]
            
    return SSMFunctionMetadata(
        id=row["id"],
        name=row["Name"],
        model=_parse_enum(DamageModel, row["Model"]),
        country=_parse_enum(Country, row["Country"]),
        function_type=_parse_enum(SSMFunctionType, row["Function type"]),
        damage_level=_parse_enum(DamageLevel, row["Level"]),
        return_period_protection=int(row["Flood Protection Return Period"]) if not pd.isna(row["Flood Protection Return Period"]) else None,
        l1_category=_parse_enum(L1FunctionCategory, row["Category group"]),
        l2_categories=[parsed for cat, parsed in parsed_l2_cats if parsed is not None],
        l3_categories=[parsed for cat, parsed in parsed_l3_cats if parsed is not None],
        source_description=row.get("Description of category by source"),
        method=_parse_enum(SSMFunctionMethod, row["Method"]),
        scale=_parse_enum(SSMFunctionScale, row["Scale"]),
        notes=row.get("Notes"),
    )

def _parse_ssm_function_mapping(mapping_df: pd.DataFrame) -> dict[int, SSMFunctionMetadata]:
    return {row["id"]: _parse_function_metadata(row) for _, row in mapping_df.iterrows() if str(row["Include"]).strip().lower() == "true"}

def load_ssm_functions() -> dict[int, SSMFunctionMetadata]:
    mapping_df = _load_ssm_function_mapping()
    return _parse_ssm_function_mapping(mapping_df)

METADATA = load_ssm_functions()

def _load_function_with_id(function_id: int) -> tuple[dict[float, float], IntensityUnit]:
    filepath = SSM_FUNCTIONS_PATH / f"{function_id}.csv"
    df = pd.read_csv(filepath, delimiter=",", encoding="utf-8")
    df.columns = [c.lower() for c in df.columns]
    intensity_column_name = df.columns[0]
    if intensity_column_name == "wd(m)":
        intensity_unit = IntensityUnit.DEPTH_METERS
    else:
        raise ValueError(f"Unknown intensity unit in function {function_id}: {intensity_column_name}")
    return dict(zip(df[intensity_column_name], df["factor"])), intensity_unit

def get_function_from_id(function_id: int) -> SSMFunction | None:
    metadata = METADATA.get(function_id)
    values, intensity_unit = _load_function_with_id(function_id)
    return SSMFunction(metadata=metadata, values=values, intensity_unit=intensity_unit)

def query_functions(country: Country | None = None,
                    function_type: SSMFunctionType | None = None,
                    category: L1FunctionCategory | None = None,
                    subcategory: L2FunctionCategory | None = None) -> list[SSMFunction]:
    results: list[SSMFunctionMetadata] = []
    for metadata in METADATA.values():
        if country and metadata.country != country:
            continue
        if function_type and metadata.function_type != function_type:
            continue
        if category and metadata.l1_category != category:
            continue
        if subcategory and subcategory not in metadata.l2_categories:
            continue
        results.append(metadata)
    return [get_function_from_id(m.id) for m in results]