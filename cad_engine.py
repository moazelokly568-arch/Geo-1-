import math
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import ezdxf
from ezdxf import units

from app.core.config import settings


def compute_polygon_area_and_perimeter(points: List[Dict[str, float]]) -> Dict[str, float]:
    n = len(points)
    if n < 3:
        perim = sum(
            math.hypot(points[i + 1]["x"] - points[i]["x"], points[i + 1]["y"] - points[i]["y"])
            for i in range(n - 1)
        )
        return {"area_m2": 0.0, "perimeter_m": round(perim, 3), "feddan": 0.0}

    area2 = 0.0
    perimeter = 0.0
    for i in range(n):
        j = (i + 1) % n
        area2 += points[i]["x"] * points[j]["y"]
        area2 -= points[j]["x"] * points[i]["y"]
        perimeter += math.hypot(points[j]["x"] - points[i]["x"], points[j]["y"] - points[i]["y"])

    area_m2 = abs(area2) / 2.0
    feddan = area_m2 / 4200.83
    return {
        "area_m2": round(area_m2, 3),
        "perimeter_m": round(perimeter, 3),
        "feddan": round(feddan, 4),
    }


def generate_survey_dxf(
    points: List[Dict[str, Any]],
    project_title: str = "CADASTRAL SURVEY PLAN - GEOMASAHA",
    crs_label: str = "Projected Meters (Local / UTM)",
    close_polygon: bool = True,
) -> Dict[str, Any]:
    if len(points) < 2:
        raise ValueError("يتطلب إنشاء اللوحة المساحية نقطتين على الأقل (و3 نقاط لحساب المساحة).")

    os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)
    file_id = uuid.uuid4().hex[:10]
    dxf_filename = f"GeoMasaha_SurveyPlan_{file_id}.dxf"
    dxf_path = Path(settings.ARTIFACTS_DIR) / dxf_filename

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = units.M
    msp = doc.modelspace()

    layers_spec = [
        ("01_BOUNDARY", 3),
        ("02_POINTS", 1),
        ("03_LABELS", 7),
        ("04_DIMENSIONS", 4),
        ("05_AREA_INFO", 2),
        ("06_GRID", 8),
        ("07_NORTH_ARROW", 5),
        ("08_TITLE_BLOCK", 6),
    ]
    for name, color in layers_spec:
        if name not in doc.layers:
            doc.layers.add(name, color=color)

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 10.0)
    span_y = max(max_y - min_y, 10.0)
    max_span = max(span_x, span_y)

    text_h = max(round(max_span * 0.018, 3), 0.25)
    marker_r = max(round(max_span * 0.012, 3), 0.15)
    margin = max_span * 0.25

    poly_coords = [(p["x"], p["y"]) for p in points]
    msp.add_lwpolyline(
        poly_coords,
        close=close_polygon and len(points) >= 3,
        dxfattribs={"layer": "01_BOUNDARY", "lineweight": 35},
    )

    for p in points:
        x, y = p["x"], p["y"]
        pt_id = p.get("id", "PT")
        msp.add_point((x, y), dxfattribs={"layer": "02_POINTS"})
        msp.add_circle((x, y), radius=marker_r, dxfattribs={"layer": "02_POINTS"})

        label_text = f"{pt_id} (E:{x:.2f}, N:{y:.2f})"
        if "z" in p:
            label_text += f" Z:{p['z']:.2f}"
        msp.add_text(
            label_text,
            dxfattribs={"layer": "03_LABELS", "height": text_h * 0.85},
        ).set_placement((x + marker_r * 1.4, y + marker_r * 1.4))

    seg_count = len(points) if (close_polygon and len(points) >= 3) else len(points) - 1
    for i in range(seg_count):
        p1 = points[i]
        p2 = points[(i + 1) % len(points)]
        dx = p2["x"] - p1["x"]
        dy = p2["y"] - p1["y"]
        dist = math.hypot(dx, dy)
        az_deg = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
        mid_x = (p1["x"] + p2["x"]) / 2.0
        mid_y = (p1["y"] + p2["y"]) / 2.0

        angle = math.degrees(math.atan2(dy, dx))
        if angle > 90 or angle < -90:
            angle += 180

        msp.add_text(
            f"L={dist:.2f}m | Az={az_deg:.1f}°",
            dxfattribs={"layer": "04_DIMENSIONS", "height": text_h * 0.8, "rotation": angle},
        ).set_placement((mid_x, mid_y + text_h * 0.4))

    metrics = compute_polygon_area_and_perimeter(points)
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    if len(points) >= 3 and close_polygon:
        msp.add_text(
            f"AREA = {metrics['area_m2']:,.2f} m2 ({metrics['feddan']:.4f} Feddan)",
            dxfattribs={"layer": "05_AREA_INFO", "height": text_h * 1.15},
        ).set_placement((cx - text_h * 6, cy))
        msp.add_text(
            f"PERIMETER = {metrics['perimeter_m']:,.2f} m",
            dxfattribs={"layer": "05_AREA_INFO", "height": text_h * 0.95},
        ).set_placement((cx - text_h * 5, cy - text_h * 1.6))

    frame_min_x = min_x - margin
    frame_max_x = max_x + margin
    frame_min_y = min_y - margin * 1.35
    frame_max_y = max_y + margin

    msp.add_lwpolyline(
        [
            (frame_min_x, frame_min_y),
            (frame_max_x, frame_min_y),
            (frame_max_x, frame_max_y),
            (frame_min_x, frame_max_y),
        ],
        close=True,
        dxfattribs={"layer": "08_TITLE_BLOCK", "lineweight": 50},
    )

    tb_h = margin * 0.45
    msp.add_line(
        (frame_min_x, frame_min_y + tb_h),
        (frame_max_x, frame_min_y + tb_h),
        dxfattribs={"layer": "08_TITLE_BLOCK"},
    )
    msp.add_text(
        f"PROJECT: {project_title}  |  CRS: {crs_label}  |  POINTS: {len(points)}  |  DATE: {datetime.utcnow().strftime('%Y-%m-%d')}",
        dxfattribs={"layer": "08_TITLE_BLOCK", "height": text_h * 0.95},
    ).set_placement((frame_min_x + text_h, frame_min_y + tb_h * 0.35))

    na_x = frame_max_x - margin * 0.35
    na_y = frame_max_y - margin * 0.45
    na_len = margin * 0.32
    msp.add_line((na_x, na_y - na_len * 0.5), (na_x, na_y + na_len * 0.5), dxfattribs={"layer": "07_NORTH_ARROW"})
    msp.add_lwpolyline(
        [
            (na_x - na_len * 0.15, na_y + na_len * 0.25),
            (na_x, na_y + na_len * 0.5),
            (na_x + na_len * 0.15, na_y + na_len * 0.25),
        ],
        dxfattribs={"layer": "07_NORTH_ARROW"},
    )
    msp.add_text("N", dxfattribs={"layer": "07_NORTH_ARROW", "height": text_h * 1.2}).set_placement(
        (na_x - text_h * 0.35, na_y + na_len * 0.55)
    )

    sb_x = frame_min_x + text_h
    sb_y = frame_min_y + tb_h + text_h * 1.2
    sb_len = round(max_span * 0.2, 0) or 10.0
    msp.add_line((sb_x, sb_y), (sb_x + sb_len, sb_y), dxfattribs={"layer": "08_TITLE_BLOCK"})
    msp.add_text(f"0          {sb_len/2:.0f}          {sb_len:.0f} m", dxfattribs={"layer": "08_TITLE_BLOCK", "height": text_h * 0.75}).set_placement(
        (sb_x, sb_y + text_h * 0.3)
    )

    doc.saveas(str(dxf_path))

    dwg_note = "تم إنشاء ملف DXF قياسي (R2010) قابل للفتح والتعديل مباشرة في AutoCAD وCivil 3D."
    if settings.ODA_CONVERTER_PATH and os.path.exists(settings.ODA_CONVERTER_PATH):
        subprocess.run(
            [settings.ODA_CONVERTER_PATH, settings.ARTIFACTS_DIR, settings.ARTIFACTS_DIR, "ACAD2010", "DWG", "0", "1", dxf_filename],
            check=False,
        )
        dwg_note += " كما يتوفر التحويل إلى DWG عبر محرك ODA المثبّت."

    return {
        "type": "dxf",
        "filename": dxf_filename,
        "download_url": f"/artifacts/{dxf_filename}",
        "note": dwg_note,
        "metrics": {
            "عدد النقاط": len(points),
            "المساحة (م²)": f"{metrics['area_m2']:,.2f}",
            "المساحة (فدان)": metrics["feddan"],
            "المحيط (م)": f"{metrics['perimeter_m']:,.2f}",
            "نظام الإحداثيات": crs_label,
            "عدد الطبقات (Layers)": len(layers_spec),
        },
        "preview_geometry": {
            "closed": close_polygon and len(points) >= 3,
            "points": [{"id": p.get("id", f"P{i+1}"), "x": p["x"], "y": p["y"]} for i, p in enumerate(points)],
        },
    }
