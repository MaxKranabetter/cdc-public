from enum import Enum
from pathlib import Path

class FloodScenario(Enum):
    BASELINE = 2018
    FUTURE_2050 = 2050
    FUTURE_2100 = 2100

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_FLOODMAPS_DIR = PROJECT_ROOT / "data" / "max-water-depth" / "baseline"

DEFAULT_FLOODMAPS = {
    FloodScenario.BASELINE: {
        10: str(BASELINE_FLOODMAPS_DIR / "grote_kans.tif"),
        100: str(BASELINE_FLOODMAPS_DIR / "middelgrote_kans.tif"),
        1000: str(BASELINE_FLOODMAPS_DIR / "kleine_kans.tif"),
        10000: str(BASELINE_FLOODMAPS_DIR / "zeer_kleine_kans.tif"),
        100000: str(BASELINE_FLOODMAPS_DIR / "extreem_kleine_kans.tif")
    }
}