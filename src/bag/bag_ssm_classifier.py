from collections import defaultdict
import logging

import pandas as pd

from src.bag.models import BAGBuildingData, VerblijfsobjectFeature
from src.ssm.models import Country, L1FunctionCategory as L1, L2FunctionCategory as L2, L3FunctionCategory as L3, SSMFunctionMetadata
from shapely.wkt import loads
from shapely.geometry import Polygon, shape
import json

BAG_TO_MAIN_CATEGORY = {
    'woonfunctie': 'RESIDENTIAL',
    'kantoorfunctie': 'COMMERCIAL',
    'winkelfunctie': 'COMMERCIAL',
    'bijeenkomstfunctie': 'COMMERCIAL',
    'logiesfunctie': 'COMMERCIAL',
    'onderwijsfunctie': 'COMMERCIAL',
    'gezondheidszorgfunctie': 'COMMERCIAL',
    'sportfunctie': 'COMMERCIAL',
    'celfunctie': 'COMMERCIAL',
    'industriefunctie': 'INDUSTRIAL',
    'overige gebruiksfunctie': 'INFRASTRUCTURE'
}

SCORING_MATRIX = {
    "RESIDENTIAL": {
        'L1': {L1.RESIDENTIAL: 1.0},
        
        'L2_rules': lambda num_vbos, year, sqm, doelen, spatial, vbos: {
            L2.APARTMENTS: 0.95 if (num_vbos > 2) or (sqm > 500 and spatial.get('touching_count') >= 2) else 0.05,
            L2.SINGLE_FAMILY: 0.95 if (num_vbos <= 2) else 0.05,
        },
        
        'L3_rules': {
            L2.SINGLE_FAMILY: lambda num_vbos, year, sqm, doelen, spatial, vbos: {
                L3.FULLY_DETACHED: 0.9 if spatial.get('touching_count') == 0 else 0.0,
                L3.SEMI_DETACHED: 0.9 if spatial.get('touching_count') == 1 else 0.0,
                L3.TERRACED: 0.9 if spatial.get('touching_count') >= 2 else 0.0,
                L2.GENERIC: 0.1 if 'touching_count' in spatial else 1.0,
                None: 0.1 if 'touching_count' in spatial else 1.0
            },
            L2.APARTMENTS: lambda num_vbos, year, sqm, doelen, spatial, vbos: {
                L2.GENERIC: 1.0, None: 1.0
            }
        }
    },

    "COMMERCIAL": {
        'L1': {L1.EMPLOYMENT: 1.0},
        
        'L2_rules': lambda num_vbos, year, sqm, doelen, spatial, vbos: {
            L2.EDUCATION: 0.9 if 'onderwijsfunctie' in doelen else 0.0,
            L2.HOSPITAL: 0.9 if 'gezondheidszorgfunctie' in doelen else 0.0,
            L2.OFFICE: 0.8 if 'kantoorfunctie' in doelen else 0.0,
            L2.COMMERCIAL: 0.8 if 'winkelfunctie' in doelen or 'bijeenkomstfunctie' in doelen else 0.0,
            L2.GENERIC: 0.1, None: 0.1
        },
        
        'L3_rules': {
            L2.COMMERCIAL: lambda num_vbos, year, sqm, doelen, spatial, vbos: {
                L3.SPORTS_AND_RECREATION: 0.9 if 'sportfunctie' in doelen else 0.0,
                L3.HORECA: 0.8 if 'logiesfunctie' in doelen or ('bijeenkomstfunctie' in doelen and spatial.get('neighbour_uses', {}).get('woonfunctie', 0) > 0.5) else 0.0,
                L3.BANK: 0.4 if 'kantoorfunctie' in doelen and 'winkelfunctie' in doelen else 0.0,
                L2.GENERIC: 0.2, None: 0.2
            },
            L2.OFFICE: lambda num_vbos, year, sqm, doelen, spatial, vbos: {
                L3.SOCIAL_INFRASTRUCTURE: 0.7 if spatial.get('neighbour_uses', {}).get('woonfunctie', 0) > 0.6 else 0.1,
                L2.GENERIC: 0.5, None: 0.5
            },
            L2.EDUCATION: lambda num_vbos, year, sqm, doelen, spatial, vbos: {
                L3.LIBRARY: 0.6 if 'bijeenkomstfunctie' in doelen else 0.0,
                L3.SCHOOL: 0.8 if get_vbo_area('onderwijsfunctie', vbos) >= 500 else 0.2,
                L2.GENERIC: 0.1, None: 0.1
            }
        }
    },

    "INDUSTRIAL": {
        'L1': {L1.EMPLOYMENT: 1.0},
        
        'L2_rules': lambda num_vbos, year, sqm, doelen, spatial, vbos: {
            L2.AGRICULTURE: 0.85 if spatial.get('min_distance_m') > 30 and spatial.get('neighbour_uses', {}).get('woonfunctie', 0) < 0.1 else 0.0,
            L2.INDUSTRIAL: 0.9 if 'industriefunctie' in doelen else 0.4,
            L2.GENERIC: 0.1, None: 0.1
        },
        
        'L3_rules': {
            L2.INDUSTRIAL: lambda num_vbos, year, sqm, doelen, spatial, vbos: {
                L3.WAREHOUSE: 0.8 if get_vbo_area('industriefunctie', vbos) > 1500 and spatial.get('neighbour_uses', {}).get('woonfunctie', 0) < 0.2 else 0.2,
                L2.GENERIC: 0.3, None: 0.3
            }
        }
    },

    "INFRASTRUCTURE": {
        'L1': {L1.INFRASTRUCTURE: 1.0},
        'L2_rules': lambda num_vbos, year, sqm, doelen, spatial, vbos: {
            L2.TRANSPORTATION: 0.5 if 'overige gebruiksfunctie' in doelen else 0.2,
            L2.WATER: 0.3, L2.GENERIC: 0.5, None: 0.5
        },
        'L3_rules': {}
    }
}

def get_vbo_area(target_doel: str, vbos: list[VerblijfsobjectFeature]) -> float:
    """Calculates the total oppervlakte for a specific gebruiksdoel across all num_vbos."""
    if not vbos:
        return 0.0
    total = 0.0
    for vbo in vbos:
        unit_doelen = [d.strip() for d in (vbo.properties.gebruiksdoel or "").split(',')]
        if target_doel in unit_doelen:
            total += (vbo.properties.oppervlakte or 0)
    return total

class BAGSSMClassifier:
    
    def __init__(self, damage_functions: dict[int, SSMFunctionMetadata]):
        self.damage_functions = damage_functions
        self.matrix = SCORING_MATRIX
        
    def _safe_load_geom(self, geom: str | Polygon) -> Polygon | None:
        if isinstance(geom, Polygon):
            return geom
        if not geom:
            return None
        try:
            if geom.strip().startswith('{'):
                geom_dict = json.loads(geom)
                return shape(geom_dict)
            else:
                return loads(geom)
        except Exception as e:
            logging.error(f"Error parsing geometry string: {e}")
            return None

    def get_sqm_from_geometry(self, geometry: str | Polygon) -> float:
        """Extract square meters from geometry string (WKT or GeoJSON format)."""
        parsed_geom = self._safe_load_geom(geometry)
        if parsed_geom is None:
            return 0.0
        return parsed_geom.area
    
    def build_spatial_context(self, building_geometry: str | Polygon, neighbouring_objects: list[BAGBuildingData]) -> dict:
        touching_count = 0
        distances = []
        neighbour_uses = defaultdict(int)
        neighbour_years = []
        building_geom = self._safe_load_geom(building_geometry)
        if building_geom is not None:
            for neighbour in neighbouring_objects:
                neighbour_geoms = neighbour.pand.geometry.to_shapely()
                if len(neighbour_geoms) > 1:
                    logging.warning(f"Neighbour with id {neighbour.id} has multiple geometries. Using the first one for spatial context.")
                neighbour_geom = neighbour_geoms[0]
                if building_geom.buffer(0.1).overlaps(neighbour_geom): # allow a 10cm buffer to account for minor digitization gaps
                    touching_count += 1
                distances.append(building_geom.distance(neighbour_geom))
                for doel in (neighbour.pand.properties.gebruiksdoel or "").split(','):
                    if len(doel.strip()) == 0:
                        continue 
                    neighbour_uses[doel.strip()] += 1
                if neighbour.pand.properties.bouwjaar:
                    neighbour_years.append(neighbour.pand.properties.bouwjaar)
        return {
            'touching_count': touching_count,
            'min_distance_m': min(distances) if distances else float('inf'),
            'median_neighbour_year': pd.Series(neighbour_years).median() if neighbour_years else None,
            'neighbour_year_range': (min(neighbour_years), max(neighbour_years)) if neighbour_years else (None, None),
            'neighbour_uses': neighbour_uses
        }

    def match_functions_to_bag_object(self, bag_data: pd.Series, ci: float = 0.4, max_functions: int = 10) -> list[tuple[SSMFunctionMetadata, float]]:
        doelen = bag_data.get('gebruiksdoel', '').split(',')
        vbos = bag_data.get('verblijfsobjecten', [])
        scores = self.score_building(
            num_vbos=bag_data.get('aantal_verblijfsobjecten', len(vbos)),
            year=bag_data.get('bouwjaar', 0) or 0,
            sqm=self.get_sqm_from_geometry(bag_data.get('geometry', '')),
            verblijfsobjecten=vbos,
            doelen=doelen,
            spatial=self.build_spatial_context(bag_data.get('geometry', ''), bag_data.get('neighbourhood', []))
        )
        weighted_functions = self.weight_functions(scores)
        sorted_functions = sorted(weighted_functions.items(), key=lambda x: x[1], reverse=True)
        selected_functions = []
        while sum([f[1] for f in selected_functions]) < ci < 3 and len(selected_functions) < max_functions and sorted_functions:
            func_id, weight = sorted_functions.pop(0)
            selected_functions.append((self.damage_functions[func_id], weight))
        return selected_functions

    def map_bag_to_main_categories(self, pand_area: float, pand_uses: list[str], verblijfsobjecten: list[VerblijfsobjectFeature]) -> dict[str, float]:
        category_areas = defaultdict(float)
        total_area = 0.0

        if verblijfsobjecten:
            for vbo in verblijfsobjecten:
                # Extract uses specific to this single unit
                vbo_uses = [u.strip() for u in (vbo.properties.gebruiksdoel or "").split(',') if u.strip() in BAG_TO_MAIN_CATEGORY]
                area = vbo.properties.oppervlakte
                
                # Check if area is populated and valid
                if area is None or area <= 0:
                    # assume equal distribution if area is missing/invalid
                    area = pand_area / len(verblijfsobjecten)
                # If a single unit has multiple uses, distribute its area equally
                area_per_use = area / len(vbo_uses) 
                
                for use in vbo_uses:
                    main_cat = BAG_TO_MAIN_CATEGORY[use]
                    category_areas[main_cat] += area_per_use
                    total_area += area_per_use
                        
        if total_area > 0:
            return {cat: area / total_area for cat, area in category_areas.items()}

        category_weights = defaultdict(float)
        valid_uses = [u.strip() for u in pand_uses if u.strip() in BAG_TO_MAIN_CATEGORY]
        
        if not valid_uses:
            return {}

        weight_per_use = 1.0 / len(valid_uses)
        for use in valid_uses:
            main_cat = BAG_TO_MAIN_CATEGORY[use]
            category_weights[main_cat] += weight_per_use

        return dict(category_weights)

    def _normalize(self, scores_dict: dict) -> dict:
        total = sum(scores_dict.values())
        if total > 0:
            return {k: v / total for k, v in scores_dict.items() if v > 0}
        return {}

    def score_building(self,
                       num_vbos: int,
                       year: int,
                       sqm: float,
                       verblijfsobjecten: list[VerblijfsobjectFeature],
                       doelen: list,
                       spatial: dict) -> dict:
        main_categories = self.map_bag_to_main_categories(sqm, doelen, verblijfsobjecten)
        final_scores = {'L1': {}, 'L2': {}, 'L3': {}}
        
        valid_cats = [(c, w) for c, w in main_categories.items() if c in self.matrix]
        if not valid_cats:
            return final_scores

        for cat, base_weight in valid_cats:
            rules = self.matrix[cat]
            
            for l1_cat, l1_prob in rules['L1'].items():
                score = l1_prob * base_weight
                final_scores['L1'][l1_cat] = final_scores['L1'].get(l1_cat, 0.0) + score
                
                if 'L2_rules' in rules:
                    raw_l2 = rules['L2_rules'](num_vbos, year, sqm, doelen, spatial, verblijfsobjecten)
                    norm_l2 = self._normalize(raw_l2)
                    
                    for l2_cat, l2_mod in norm_l2.items():
                        l2_score = score * l2_mod # Parent L1 score * normalized modifier
                        final_scores['L2'][l2_cat] = final_scores['L2'].get(l2_cat, 0.0) + l2_score
                        
                        if 'L3_rules' in rules and l2_cat in rules['L3_rules']:
                            raw_l3 = rules['L3_rules'][l2_cat](num_vbos, year, sqm, doelen, spatial, verblijfsobjecten)
                            norm_l3 = self._normalize(raw_l3)
                            
                            for l3_cat, l3_mod in norm_l3.items():
                                l3_score = l2_score * l3_mod # Parent L2 score * normalized modifier
                                final_scores['L3'][l3_cat] = final_scores['L3'].get(l3_cat, 0.0) + l3_score

        return final_scores
    
    def add_country_weight(self, f: SSMFunctionMetadata, current_weight: float, building_country: Country) -> float:
        w = 1.0 if f.country == building_country else 0.33
        return current_weight * w
    
    def weight_functions(self, scores: dict) -> dict[int, float]:
        weighted_functions = defaultdict(float)
        for func_id, func in self.damage_functions.items():
            score = scores['L1'].get(func.l1_category, 0.0)
            
            l2_scores = scores['L2']
            for l2_cat in func.l2_categories:
                l2_score = l2_scores.get(l2_cat, 0.0)
                score += l2_score * 2 / len(func.l2_categories)
            
            l3_scores = scores['L3']
            for l3_cat in func.l3_categories:
                l3_score = l3_scores.get(l3_cat, 0.0)
                score += l3_score * 3 / len(func.l3_categories) # penalise having many L3 categories (function is less specific)

            weighted_functions[func_id] = self.add_country_weight(func, score, Country.NLD) # hard-coding NLD for now
        
        # Normalize final function weights
        total_weight = sum(weighted_functions.values())
        if total_weight > 0:
            return {func: weight / total_weight for func, weight in weighted_functions.items()}
        return {}