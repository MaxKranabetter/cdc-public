import logging
from typing import Any

import branca.colormap as cm
import folium
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import box

import geopandas as gpd

from src.calc.damage_scanner_interface import BuildingClassifierType, BuildingDataInput, DamageScannerInputs, DamageScannerInterface

class DamageVisualiser:

    def __init__(
        self,
        inputs: DamageScannerInputs,
        selected_return_period: int = 1000,
        surroundings_buffer_m: float = 5000,
    ):
        self.damage_scanner = DamageScannerInterface(inputs)
        self.selected_return_period = selected_return_period
        self.surroundings_buffer_m = surroundings_buffer_m

    def _validate_ead_data(self, ead: pd.DataFrame) -> gpd.GeoDataFrame:
        if not isinstance(ead, gpd.GeoDataFrame):
            ead = gpd.GeoDataFrame(ead, geometry="geometry")

        if ead.empty:
            raise ValueError("EAD result is empty; cannot render map.")

        if "geometry" not in ead.columns:
            raise ValueError("EAD result does not contain a 'geometry' column.")

        if ead.crs is None:
            raise ValueError("EAD geometries are missing CRS information.")

        if "average_ead" not in ead.columns:
            logging.warning("EAD result does not contain a 'risk' column; polygons will use a fallback style.")

        return ead

    def _get_metric_crs(self, gdf: gpd.GeoDataFrame) -> Any:
        axis_info = getattr(gdf.crs, "axis_info", None)
        if axis_info and axis_info[0].unit_name.lower().startswith("met"):
            return gdf.crs
        estimated = gdf.estimate_utm_crs()
        if estimated is None:
            raise ValueError("Could not determine a projected CRS for 5 km buffering.")
        return estimated

    def _get_buffered_extent(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        metric_crs = self._get_metric_crs(gdf)
        gdf_metric = gdf.to_crs(metric_crs)
        minx, miny, maxx, maxy = gdf_metric.total_bounds
        buffered_box = box(
            minx - self.surroundings_buffer_m,
            miny - self.surroundings_buffer_m,
            maxx + self.surroundings_buffer_m,
            maxy + self.surroundings_buffer_m,
        )
        return gpd.GeoDataFrame({"geometry": [buffered_box]}, crs=metric_crs)

    def _clip_floodmap_to_extent(
        self,
        floodmap_path: str,
        extent_gdf: gpd.GeoDataFrame,
    ) -> tuple[np.ndarray, Any, Any, float | int | None]:
        with rasterio.open(floodmap_path) as src:
            extent_in_raster_crs = extent_gdf.to_crs(src.crs)
            clipped, clipped_transform = mask(
                src,
                extent_in_raster_crs.geometry,
                crop=True,
                all_touched=True,
            )
            if clipped.size == 0 or clipped.shape[1] == 0 or clipped.shape[2] == 0:
                raise ValueError("Floodmap clipping returned an empty raster window.")
            clipped_data = clipped[0]
            return clipped_data, clipped_transform, src.crs, src.nodata

    def _reproject_raster_to_wgs84(
        self,
        raster_data: np.ndarray,
        src_transform: Any,
        src_crs: Any,
        nodata: float | int | None,
    ) -> tuple[np.ndarray, Any]:
        height, width = raster_data.shape
        src_bounds = array_bounds(height, width, src_transform)
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_crs,
            "EPSG:4326",
            width,
            height,
            *src_bounds,
        )
        dst = np.empty((dst_height, dst_width), dtype=np.float32)
        reproject(
            source=raster_data,
            destination=dst,
            src_transform=src_transform,
            src_crs=src_crs,
            src_nodata=nodata,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            dst_nodata=nodata,
            resampling=Resampling.bilinear,
        )
        return dst, dst_transform

    def _raster_to_rgba(
        self,
        raster_data: np.ndarray,
        nodata: float | int | None,
    ) -> tuple[np.ndarray, float, float]:
        data = raster_data.astype(np.float32)
        invalid_mask = np.isnan(data)
        if nodata is not None:
            invalid_mask = invalid_mask | (data == nodata)

        valid_data = data[~invalid_mask]
        if valid_data.size == 0:
            raise ValueError("Floodmap raster contains no valid cells in the requested extent.")

        vmin = np.percentile(valid_data, 2)
        vmax = np.percentile(valid_data, 98)
        if vmax <= vmin:
            vmax = vmin + 1.0

        norm = np.clip((data - vmin) / (vmax - vmin), 0.0, 1.0)
        # Flip intensity direction so low values are lighter and high values are darker.
        inv_norm = 1.0 - norm

        rgba = np.zeros((data.shape[0], data.shape[1], 4), dtype=np.uint8)
        # Stronger contrast at both ends: bright cyan (low) to deep navy (high).
        rgba[..., 0] = (5 + inv_norm * 95).astype(np.uint8)
        rgba[..., 1] = (20 + inv_norm * 210).astype(np.uint8)
        rgba[..., 2] = (85 + inv_norm * 170).astype(np.uint8)
        rgba[..., 3] = (70 + norm * 170).astype(np.uint8)
        rgba[invalid_mask, 3] = 0
        return rgba, float(vmin), float(vmax)

    def _add_flood_legend(self, fmap: folium.Map, vmin: float, vmax: float) -> None:
        flood_colormap = cm.LinearColormap(
            colors=["#64e6ff", "#1f7be6", "#061b78"],
            vmin=vmin,
            vmax=vmax,
        )
        flood_colormap.caption = f"Flood depth RP {self.selected_return_period} (m)"
        flood_colormap.add_to(fmap)

    def _add_ead_polygons(self, fmap: folium.Map, ead_wgs84: gpd.GeoDataFrame) -> None:
        has_risk = "average_ead" in ead_wgs84.columns and not ead_wgs84["average_ead"].isna().all()
        if has_risk:
            risk_min = float(ead_wgs84["average_ead"].min())
            risk_max = float(ead_wgs84["average_ead"].max())
            if risk_max <= risk_min:
                risk_max = risk_min + 1.0
            colormap = cm.linear.YlOrRd_09.scale(risk_min, risk_max)
            colormap.caption = "EAD risk"
            colormap.add_to(fmap)
        else:
            colormap = None

        geojson_data = ead_wgs84.to_json()

        def style_function(feature: dict[str, Any]) -> dict[str, Any]:
            if colormap is None:
                fill_color = "#fdae61"
            else:
                risk_value = feature["properties"].get("average_ead")
                fill_color = colormap(risk_value) if risk_value is not None else "#fdae61"
            return {
                "fillColor": fill_color,
                "color": "#3b2f2f",
                "weight": 1,
                "fillOpacity": 0.65,
            }

        tooltip_fields = [field for field in ["osm_id", "obj_type", "average_ead"] if field in ead_wgs84.columns]

        folium.GeoJson(
            data=geojson_data,
            name="EAD polygons",
            style_function=style_function,
            highlight_function=lambda _: {"weight": 2, "fillOpacity": 0.85},
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_fields, localize=True),
            # Placeholder for future click action wiring.
            popup=None,
        ).add_to(fmap)

    def build_map(
        self,
        ead_raw: pd.DataFrame,
        output_html: str | None = None,
    ) -> folium.Map:
        ead = self._validate_ead_data(ead_raw)

        floodmap_dict = self.damage_scanner.floodmap_interface.get_floodmap_dict()
        if self.selected_return_period not in floodmap_dict:
            raise ValueError(f"Unsupported return period '{self.selected_return_period}'. Available: {sorted(floodmap_dict.keys())}")
        floodmap_path = floodmap_dict[self.selected_return_period]

        extent_gdf = self._get_buffered_extent(ead)
        clipped_raster, clipped_transform, raster_crs, nodata = self._clip_floodmap_to_extent(floodmap_path, extent_gdf)
        raster_wgs84, raster_wgs84_transform = self._reproject_raster_to_wgs84(
            clipped_raster,
            clipped_transform,
            raster_crs,
            nodata,
        )
        raster_rgba, raster_vmin, raster_vmax = self._raster_to_rgba(raster_wgs84, nodata)

        ead_wgs84 = ead.to_crs("EPSG:4326")
        center = ead_wgs84.geometry.union_all().centroid

        west, south, east, north = array_bounds(
            raster_wgs84.shape[0],
            raster_wgs84.shape[1],
            raster_wgs84_transform,
        )

        fmap = folium.Map(
            location=[center.y, center.x],
            zoom_start=16,
            tiles="CartoDB positron",
            control_scale=True,
            min_zoom=12,
            max_bounds=True,
            min_lat=south,
            max_lat=north,
            min_lon=west,
            max_lon=east,
        )
        folium.raster_layers.ImageOverlay(
            image=raster_rgba,
            bounds=[[south, west], [north, east]],
            name=f"Flood depth RP {self.selected_return_period}",
            opacity=0.65,
            interactive=False,
            zindex=1,
        ).add_to(fmap)
        self._add_flood_legend(fmap, raster_vmin, raster_vmax)

        self._add_ead_polygons(fmap, ead_wgs84)
        folium.LayerControl(collapsed=False).add_to(fmap)

        if output_html is not None:
            fmap.save(output_html)

        return fmap

    def main(self, output_html: str = r"data\output\damage_visualisation.html") -> folium.Map:
        ead_raw = self.damage_scanner.get_damages()
        return self.build_map(ead_raw, output_html=output_html)

if __name__ == "__main__":
    inputs = DamageScannerInputs(building_inputs=[
        BuildingDataInput(address="Sterremosstraat 8, 1441 LT Purmerend", building_classifier_type=BuildingClassifierType.BAG),
        BuildingDataInput(address="68 Mont Saint Michel Purmerend, North Holland", building_classifier_type=BuildingClassifierType.BAG)
    ])
    visualiser = DamageVisualiser(inputs)
    visualiser.main()
    print("Saved interactive damage map to data\\output\\damage_visualisation.html")