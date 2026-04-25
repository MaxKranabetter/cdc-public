import pandas as pd
from damagescanner.core import DamageScanner

import geopandas as gpd

from src.calc.building_data_interface import BuildingDataInterface
from src.calc.damage_function_interface import DamageFunctionInterface
from src.calc.floodmap_interface import FloodmapInterface
from src.calc.max_damage_interface import MaxDamageInterface
from src.calc.models import DamageScannerInputs

class DamageScannerInterface:

    def __init__(self, inputs: DamageScannerInputs):
        self.damage_scanner = None
        self.object_col = 'object_type' # this should be the name of the column in the building data that contains the object/landuse type, which is used to link to the damage curves
        self.damage_function_interface = DamageFunctionInterface()
        self.floodmap_interface = FloodmapInterface(override_floodmaps=inputs.override_floodmaps)
        self.building_data_interface = BuildingDataInterface(
            inputs.building_inputs,
            function_interface=self.damage_function_interface,
            coverage_floodmap_path=self.floodmap_interface.get_representative_floodmap_path(),
        )
        self.max_damage_interface = MaxDamageInterface(object_col=self.object_col)

    def _init_damage_scanner(self) -> DamageScanner:
        if self.damage_scanner is not None:
            return self.damage_scanner
        building_data = self.building_data_interface.get_building_data(as_fp=False)
        damage_functions = self.damage_function_interface.get_damage_functions()
        max_damage_data = self.max_damage_interface.get_max_damage_data(
            selected_curves=[curve for curve in self.damage_function_interface.damage_functions.values() if str(curve.metadata.id) in damage_functions.columns[1:]]
        )
        floodmap_data = self.floodmap_interface.get_base_floodmap_data()
        
        self.damage_scanner = DamageScanner(floodmap_data, building_data, damage_functions, max_damage_data)
        return self.damage_scanner

    def _get_ead(self) -> pd.DataFrame | None:
        ds = self._init_damage_scanner()
        floodmap_dict = self.floodmap_interface.get_floodmap_dict()
        return ds.risk(floodmap_dict)#, object_col=self.object_col) # type: ignore
    
    def get_damages(self) -> gpd.GeoDataFrame:
        ead = self._get_ead()

        # convert risk value to annualised damages
        building_geometries = ead.set_index("osm_id").geometry.to_dict()
        building_areas = {osm_id: geom.area for osm_id, geom in building_geometries.items()}
        ead["annualised_damage"] = ead.apply(lambda row: row["risk"] * building_areas.get(row["osm_id"], 0), axis=1)
        ead.pop("risk")

        # pivot data
        # input format: osm_id (building ID), obj_type (damage function), geometry, risk
        # output format: osm_id, {unique obj_type values as columns}, geometry, risk
        damage_data = ead.pivot_table(index=['osm_id', 'geometry'], columns='object_type', values='annualised_damage').reset_index()
        damage_data["average_ead"] = damage_data[[col for col in damage_data.columns if col not in ['osm_id', 'geometry']]].mean(axis=1, skipna=True)
        damage_gdf = gpd.GeoDataFrame(damage_data, geometry='geometry', crs=ead.crs)
        return damage_gdf