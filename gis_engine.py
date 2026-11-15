import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from app.core.config import settings


def infer_utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 + zone) if lat >= 0 else (32700 + zone)


def points_to_geodataframe(
    points: List[Dict[str, float]],
    geom_type: str = "polygon",
    source_epsg: Optional[int] = None,
) -> gpd.GeoDataFrame:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]

    if source_epsg is None:
        if all(-180 <= x <= 180 for x in xs) and all(-90 <= y <= 90 for y in ys):
            source_epsg = 4326
        else:
            source_epsg = 32636

    if geom_type == "polygon" and len(points) >= 3:
        geom = [Polygon([(p["x"], p["y"]) for p in points])]
        gdf = gpd.GeoDataFrame({"name": ["Parcel_Boundary"], "vertices": [len(points)]}, geometry=geom, crs=f"EPSG:{source_epsg}")
    elif geom_type == "line" and len(points) >= 2:
        geom = [LineString([(p["x"], p["y"]) for p in points])]
        gdf = gpd.GeoDataFrame({"name": ["Survey_Line"], "vertices": [len(points)]}, geometry=geom, crs=f"EPSG:{source_epsg}")
    else:
        geom = [Point(p["x"], p["y"]) for p in points]
        ids = [p.get("id", f"P{i+1}") for i, p in enumerate(points)]
        gdf = gpd.GeoDataFrame({"point_id": ids}, geometry=geom, crs=f"EPSG:{source_epsg}")

    return gdf


def run_spatial_analysis(
    gdf: gpd.GeoDataFrame,
    operation: str = "summary",
    buffer_meters: float = 100.0,
    overlay_gdf: Optional[gpd.GeoDataFrame] = None,
    overlay_how: str = "intersection",
) -> Dict[str, Any]:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    centroid = gdf_wgs84.unary_union.centroid
    utm_epsg = infer_utm_epsg(centroid.x, centroid.y)

    gdf_utm = gdf_wgs84.to_crs(f"EPSG:{utm_epsg}")

    if operation == "buffer":
        result_utm = gdf_utm.copy()
        result_utm["geometry"] = gdf_utm.buffer(buffer_meters)
        result_utm["buffer_m"] = buffer_meters
    elif operation == "overlay" and overlay_gdf is not None:
        ov_utm = overlay_gdf.to_crs(f"EPSG:{utm_epsg}")
        result_utm = gpd.overlay(gdf_utm, ov_utm, how=overlay_how)
    else:
        result_utm = gdf_utm

    total_area_m2 = float(result_utm.geometry.area.sum())
    total_length_m = float(result_utm.geometry.length.sum())

    result_wgs84 = result_utm.to_crs("EPSG:4326")
    geojson_dict = json.loads(result_wgs84.to_json())

    os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)
    out_name = f"GeoMasaha_GIS_{operation}_{uuid.uuid4().hex[:8]}.geojson"
    out_path = Path(settings.ARTIFACTS_DIR) / out_name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, ensure_ascii=False, indent=2)

    return {
        "type": "geojson",
        "filename": out_name,
        "download_url": f"/artifacts/{out_name}",
        "geojson": geojson_dict,
        "metrics": {
            "نوع التحليل": operation.upper(),
            "نطاق UTM / EPSG": f"EPSG:{utm_epsg}",
            "عدد المعالم (Features)": len(result_wgs84),
            "المساحة الكلية (م²)": f"{total_area_m2:,.2f}",
            "المساحة (كم²)": f"{total_area_m2 / 1_000_000:,.6f}",
            "إجمالي الأطوال/المحيط (م)": f"{total_length_m:,.2f}",
        },
    }
