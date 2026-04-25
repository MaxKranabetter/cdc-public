from enum import Enum

class FloodScenario(Enum):
    BASELINE = 2018
    FUTURE_2050 = 2050
    FUTURE_2100 = 2100

DEFAULT_FLOODMAPS = {
    FloodScenario.BASELINE: {
        10: r"data\max-water-depth\baseline\grote_kans.tif",
        100: r"data\max-water-depth\baseline\middelgrote_kans.tif",
        1000: r"data\max-water-depth\baseline\kleine_kans.tif",
        10000: r"data\max-water-depth\baseline\zeer_kleine_kans.tif",
        100000: r"data\max-water-depth\baseline\extreem_kleine_kans.tif"
    }
}