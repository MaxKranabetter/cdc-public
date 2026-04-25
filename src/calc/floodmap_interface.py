from pathlib import Path

from src.calc.file_mapping import DEFAULT_FLOODMAPS, FloodScenario


class FloodmapInterface:

    def __init__(self, override_floodmaps: dict[int, str] | None = None):
        floodmaps = DEFAULT_FLOODMAPS[FloodScenario.BASELINE] if override_floodmaps is None else override_floodmaps
        self.available_floodmaps = self._resolve_floodmap_paths(floodmaps)

    def _resolve_floodmap_paths(self, floodmaps: dict[int, str]) -> dict[int, str]:
        project_root = Path(__file__).resolve().parents[2]
        resolved_paths: dict[int, str] = {}
        for return_period, floodmap_path in floodmaps.items():
            path_obj = Path(floodmap_path)
            resolved_paths[return_period] = str(path_obj if path_obj.is_absolute() else project_root / path_obj)
        return resolved_paths

    def get_base_floodmap_data(self) -> str:
        # for now we just return the path to the base floodmap data, but this could be extended to include logic for selecting different floodmaps based on user input, or for loading the floodmap data into memory if needed
        return self.available_floodmaps[1000]
    
    def get_floodmap_dict(self) -> dict[int, str]:
        return self.available_floodmaps

    def get_representative_floodmap_path(self) -> str:
        if len(self.available_floodmaps) == 0:
            raise ValueError("No floodmaps are configured for coverage validation.")

        preferred_return_periods = [100000, 10000, 1000, 100, 10]
        for return_period in preferred_return_periods:
            if return_period in self.available_floodmaps:
                return self.available_floodmaps[return_period]

        first_key = sorted(self.available_floodmaps.keys())[0]
        return self.available_floodmaps[first_key]