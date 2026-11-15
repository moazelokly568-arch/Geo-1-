from pathlib import Path
import ezdxf
from app.services.cad_engine import generate_survey_dxf
from app.services.gis_engine import points_to_geodataframe, run_spatial_analysis
from app.services.surveying_calc import (
    adjust_closed_traverse_bowditch,
    latlon_to_utm,
    solve_differential_leveling,
)


def test_dxf_generation_and_layers():
    pts = [
        {"id": "P1", "x": 310000.0, "y": 3320000.0},
        {"id": "P2", "x": 310050.0, "y": 3320000.0},
        {"id": "P3", "x": 310050.0, "y": 3320040.0},
        {"id": "P4", "x": 310000.0, "y": 3320040.0},
    ]
    res = generate_survey_dxf(pts, project_title="TEST PARCEL")
    assert res["metrics"]["المساحة (م²)"] == "2,000.00"
    assert res["metrics"]["المحيط (م)"] == "180.00"

    dxf_disk_path = Path("./storage/artifacts") / res["filename"]
    assert dxf_disk_path.exists()
    doc = ezdxf.readfile(str(dxf_disk_path))
    layer_names = {l.dxf.name for l in doc.layers}
    assert {"01_BOUNDARY", "02_POINTS", "04_DIMENSIONS", "07_NORTH_ARROW", "08_TITLE_BLOCK"}.issubset(layer_names)


def test_gis_buffer_and_epsg():
    pts = [{"id": "C1", "x": 31.2357, "y": 30.0444}]
    gdf = points_to_geodataframe(pts, geom_type="point")
    out = run_spatial_analysis(gdf, operation="buffer", buffer_meters=100.0)
    assert out["metrics"]["نطاق UTM / EPSG"] == "EPSG:32636"
    assert len(out["geojson"]["features"]) == 1


def test_surveying_calculations():
    utm = latlon_to_utm(30.0444, 31.2357)
    assert utm["epsg"] == "EPSG:32636"

    lvl = solve_differential_leveling(25.400, [
        {"name": "BM1", "bs": 1.520},
        {"name": "TP1", "is": 1.840},
        {"name": "END", "fs": 2.110},
    ])
    assert lvl["arithmetic_check"]["is_verified"] is True
    assert lvl["table"][-1]["rl"] == 24.810

    trav = adjust_closed_traverse_bowditch(1000.0, 2000.0, [
        {"name": "AB", "length": 100.0, "azimuth_deg": 0.0},
        {"name": "BC", "length": 100.0, "azimuth_deg": 90.0},
        {"name": "CD", "length": 100.0, "azimuth_deg": 180.0},
        {"name": "DA", "length": 100.0, "azimuth_deg": 270.0},
    ])
    assert trav["linear_misclosure_m"] == 0.0
