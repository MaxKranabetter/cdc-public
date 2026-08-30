from collections import defaultdict

from numpy import trapezoid
import pandas as pd
from damagescanner.core import DamageScanner

import pyproj
import rasterio
import tqdm

from src.calc.overlast_damage_interface import OverlastDamageInterface
from src.calc.file_mapping import FloodType
from src.calc.building_data_interface import BuildingDataInterface
from src.calc.damage_function_interface import DamageFunctionInterface
from src.calc.floodmap_interface import FloodmapInterface
from src.calc.max_damage_interface import MaxDamageInterface
from src.calc.models import CDCInputs, CDCOutput, DamageEstimate, FloodDepth, FloodEvent

def _crs_is_meters(crs: pyproj.CRS) -> bool:
    """Check if a CRS uses meters as its unit.

    Returns:
        True if the CRS uses meters, False otherwise.
    """
    try:
        epsg_code = crs.to_epsg()
        if epsg_code is not None:
            return pyproj.CRS.from_epsg(epsg_code).axis_info[0].unit_name == "metre"
        else:
            # Fallback: check directly from the CRS axis info
            if crs.axis_info:
                return crs.axis_info[0].unit_name == "metre"
            return False
    except Exception:
        return False

class DamageScannerInterface:

    def __init__(self, inputs: CDCInputs):
        self.damage_scanner = None
        self.warnings = defaultdict(list)
        self.object_col = 'object_type' # this should be the name of the column in the building data that contains the object/landuse type, which is used to link to the damage curves
        self.damage_function_interface = DamageFunctionInterface(self.warnings)
        self.floodmap_interface = FloodmapInterface(flood_type=FloodType.OVERLAST if inputs.is_overlast else FloodType.OVERSTROMING, override_floodmaps=inputs.override_floodmaps, warnings=self.warnings)
        self.building_data_interface = BuildingDataInterface(
            inputs.building_input,
            function_interface=self.damage_function_interface,
            coverage_floodmap_path=self.floodmap_interface.get_representative_floodmap_path(),
            warnings=self.warnings
        )
        self.max_damage_interface = MaxDamageInterface(object_col=self.object_col, warnings=self.warnings)

    def _init_damage_scanner_data(self):
        self.warnings.clear()
        self.building_gdf = self.building_data_interface.get_building_gdf(is_overlast=self.floodmap_interface.flood_type == FloodType.OVERLAST)
        self.building_data = [self.damage_function_interface.bag_ssm_classifier.determine_building_data(f"building_{index}", building_row, self.building_data_interface.input.address, self.building_gdf.crs) for index, building_row in self.building_gdf.iterrows()][0]
        self.damage_functions_df, self.damage_function_package_mapping = self.damage_function_interface.get_damage_functions(self.building_data)
        if self.damage_functions_df is None:
            return None
        self.building_gdf = self.building_data_interface.match_classifier_column(
            self.building_gdf,
            self.building_data_interface.building_classifier_column,
            "building_0",
            list({str(id) for pkg in self.damage_function_package_mapping.values() for id in pkg.ids}) # only use each function once (for multiple upper floors we account for it in the max damage, not the damage functions)
        )
        self.max_damage_data, self.price_levels = self.max_damage_interface.get_max_damage_data(
            selected_curves=[curve for curve in self.damage_function_interface.damage_functions.values() if str(curve.metadata.id) in self.damage_functions_df.columns],
            building_data=self.building_data,
        )
        self.floodmap_data = self.floodmap_interface.get_base_floodmap_data()

    def _get_overlast_single_event_damage(self, floodmap_fp: str) -> pd.DataFrame | None:
        os = OverlastDamageInterface(self.building_data, floodmap_fp)
        results = []
        for index, base_building_data in self.building_gdf.iterrows():
            max_damage = self.max_damage_data.loc[self.max_damage_data['object_type'] == base_building_data.object_type, 'damage'].iloc[0] * self.building_data.polygon.area
            damage_function = self.damage_function_interface.damage_functions.get(str(base_building_data.object_type))
            if damage_function is None:
                self.warnings["general"].append(f"No damage function found for object type {base_building_data.object_type}. Skipping damage calculation for this building.")
                continue
            single_event_damage = os.calculate(maximum_damage=max_damage, damage_function=damage_function, base_building_data=base_building_data)
            if single_event_damage is not None:
                results.append(single_event_damage)
        return pd.DataFrame(results) if results else None

    def _get_single_event_damage(self, floodmap_fp: str) -> pd.DataFrame | None:
        if self.floodmap_interface.flood_type == FloodType.OVERLAST:
            return self._get_overlast_single_event_damage(floodmap_fp)
        ds = DamageScanner(floodmap_fp, self.building_gdf, self.damage_functions_df, self.max_damage_data)
        return ds.calculate(object_col=self.object_col, floodmap_fp=floodmap_fp, disable_progress=True)

    def _get_ead(self) -> pd.DataFrame | None:
        self._init_damage_scanner_data()
        if self.damage_functions_df is None:
            return None
        floodmap_dict = self.floodmap_interface.get_floodmap_dict()
        floodevents = {}
        for return_period, floodmap_fp in tqdm.tqdm(floodmap_dict.items(), desc="Calculating EAD", total=len(floodmap_dict)):
            floodevents[return_period] = self._get_single_event_damage(floodmap_fp)

        def _weighted_flood_heights(coverage_series: pd.Series, values_series: pd.Series, raster_fp: str) -> list[tuple[float, float]]:
            with rasterio.open(raster_fp) as src:
                raster_crs = src.crs
                if not _crs_is_meters(raster_crs):
                    raise ValueError(f"Raster CRS {raster_crs} is not in meters, expected a projected CRS in meters.")
                cell_size_x, cell_size_y = src.res
                cell_area_m2 = cell_size_x * cell_size_y

            coverage_row = coverage_series.iloc[0]
            value_row = values_series.iloc[0] # since we know we only ever have one building, we can assume the values will be the same for every row
            if len(coverage_row) != len(value_row):
                raise ValueError(f"Coverage and values row lengths do not match: {len(coverage_row)} vs {len(value_row)}")
            weighted_heights = [(value, coverage) for value, coverage in zip(value_row, coverage_row) if coverage > 0]
            # summarise unique heights
            unique_heights = {}
            for value, coverage in weighted_heights:
                if value in unique_heights:
                    unique_heights[value] += coverage * cell_area_m2
                else:
                    unique_heights[value] = coverage * cell_area_m2
            return [(value, coverage) for value, coverage in unique_heights.items()]

        flood_data = {
            return_period: {
                "damage": list(data["damage"]), # DamageScanner multiplies by the building footprint, but we have already done that, so to fix this we just divide by it again
                "object_id": list(data["object_type"]),
                "flood_depths": _weighted_flood_heights(data["coverage"], data["values"], floodmap_dict[return_period]),
            } for return_period, data in floodevents.items()
        }

        object_data = defaultdict(lambda: {"return_period": [], "damage": [], "flood_depths": []})

        for x, obs in flood_data.items():
            for y_val, obj_id in zip(obs["damage"], obs["object_id"]):
                object_data[obj_id]["return_period"].append(1/x if x > 1 else x) # make sure return period is represented as a fraction
                object_data[obj_id]["damage"].append(y_val)
                object_data[obj_id]["flood_depths"].append(obs["flood_depths"])

        integrals = {}
        for obj_id, damage_data in object_data.items():
            sorted_pairs = sorted(zip(damage_data["return_period"], damage_data["damage"]))
            x_vals = [p[0] for p in sorted_pairs]
            y_vals = [p[1] for p in sorted_pairs]
            integrals[obj_id] = trapezoid(y_vals, x_vals)

        summary = {
            "flood_events": [],
            "annualised_expected_damage": {}
        }
        for obj_id, data in object_data.items():
            for return_period, damage, flood_depths in zip(data["return_period"], data["damage"], data["flood_depths"]):
                if return_period in [f["return_period"] for f in summary["flood_events"]]:
                    # we already added this, so we just need to change what is unique per object (the damages)
                    return_period_index = next(i for i, f in enumerate(summary["flood_events"]) if f["return_period"] == return_period)
                    summary["flood_events"][return_period_index]["damages"][obj_id] = damage
                else:
                    summary["flood_events"].append({
                        "return_period": return_period,
                        "damages": {obj_id: damage},
                        "flood_depths": flood_depths
                    })
            summary["annualised_expected_damage"][obj_id] = float(integrals[obj_id])
        return summary

    def get_risk_profile_data_at_location(self, lat: float, lon: float) -> list[tuple[int, float]]: # (return period, flood depth)
        res = []
        floodmaps = self.floodmap_interface.get_floodmap_dict()
        for return_period, floodmap_fp in floodmaps.items():
            depth = self.floodmap_interface.get_flood_depth_at_location(lat, lon, floodmap_fp)
            if depth is not None:
                res.append((return_period, depth))
        return res
    
    def get_risk_profile_data(self) -> dict[str, list[tuple[int, float]]]: # {osm_id: [(return_period, flood_depth), ...]}
        risk_profile_data = {}
        for idx, row in self.building_gdf.iterrows():
            osm_id = row['osm_id']
            geom = row['geometry']
            centroid = geom.centroid
            lat, lon = centroid.y, centroid.x
            risk_profile_data[osm_id] = self.get_risk_profile_data_at_location(lat, lon)
        return risk_profile_data
    
    def get_damages(self) -> CDCOutput:
        damage_summary = self._get_ead()

        if damage_summary is None:
            return CDCOutput(
                building=self.building_data,
                flood_events_considered=[],
                annualised_expected_damages=[],
                warnings=self.warnings["general"]
            )

        def _flood_event_from_damage_summary(data: dict) -> FloodEvent:
            warnings = {function_id: self.warnings[int(function_id)] for function_id in data["damages"].keys()}
            return FloodEvent(
                return_period=round(1 / data["return_period"]),
                unique_flood_depths=[FloodDepth(value=depth, area_coverage=coverage) for depth, coverage in data["flood_depths"]],
                all_damages=[DamageEstimate(
                    damage_description=self.damage_function_interface.generate_description_for_function_id(key),
                    value=value,
                    ssm_function_id=int(key),
                    warnings=warnings[key],
                    price_level_year=self.price_levels[key],
                    absolute_maximum_damage=self.max_damage_data.loc[self.max_damage_data['object_type'] == key, 'damage'].iloc[0] * self.building_data.polygon.area
                ) for key, value in data["damages"].items()]
            )

        return CDCOutput(
            building=self.building_data,
            flood_events_considered=[_flood_event_from_damage_summary(d) for d in damage_summary["flood_events"]],
            annualised_expected_damages=[
                DamageEstimate(
                    damage_description=self.damage_function_interface.generate_description_for_function_id(key),
                    value=value,
                    ssm_function_id=int(key),
                    warnings=self.warnings[int(key)],
                    price_level_year=self.price_levels.get(key),
                    absolute_maximum_damage=self.max_damage_data.loc[self.max_damage_data['object_type'] == key, 'damage'].iloc[0] * self.building_data.polygon.area
                ) for key, value in damage_summary["annualised_expected_damage"].items()]
        )