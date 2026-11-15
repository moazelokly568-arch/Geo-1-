import json
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types
from PIL import Image

from app.core.config import settings
from app.services.cad_engine import generate_survey_dxf
from app.services.gis_engine import points_to_geodataframe, run_spatial_analysis

SYSTEM_ENGINEERING_PROMPT = """
أنت Geo Surveying AI – المساعد الهندسي الذكي لمنصة أكاديمية جيو مساحة (GeoMasaha Pro).
تخصصاتك الدقيقة:
1. Surveying: Total Station, Differential Leveling (Rise & Fall / HI), Closed Traverse (Bowditch), Coordinate & Area Calculations, Setting Out, As-Built.
2. GIS: ArcGIS Pro, QGIS, Spatial Analysis, Georeferencing, Geodatabase, Coordinate Systems (Geographic WGS84, UTM, ETM, EPSG), Map Design.
3. CAD: AutoCAD, Civil 3D, Layers, Blocks, Dimensions, Contours, Profiles, Cross Sections, Survey Drawings.
4. Remote Sensing: Sentinel-2, Landsat, NDVI, NDWI, NDBI, Supervised/Unsupervised Image Classification.
5. Smart Engineering Tutor: شرح البرامج الهندسية من الصفر، تقديم خطوات عملية، إنشاء تدريبات واختبارات، وتصحيح إجابات الطلاب.

قواعد الصرامة والجودة الهندسية:
- أجب بنفس لغة المستخدم (العربية أو الإنجليزية) بأسلوب هندسي احترافي منظم.
- لا تختلق أي إحداثيات أو مناسيب أو مساحات غير موجودة في بيانات المستخدم.
- اذكر دائماً الوحدات (متر، درجة، فدان) ونظام الإحداثيات (EPSG) والافتراضات بوضوح.
- عند توليد ملفات DXF أو GeoJSON، اشرح الطبقات الناتجة واطلب من المهندس مراجعة اللوحة قبل الاعتماد التنفيذي.
"""


def process_engineering_request(
    message: str,
    mode: str,
    file_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    warnings: List[str] = list((file_analysis or {}).get("warnings", []))
    artifact: Optional[Dict[str, Any]] = None
    engineered_context = ""

    points = (file_analysis or {}).get("points", [])
    wants_dxf = mode == "cad_dxf" or any(k in message.lower() for k in ["dxf", "لوحة", "أوتوكاد", "autocad", "رفع مساحي"])
    wants_gis = mode == "gis_map" or any(k in message.lower() for k in ["buffer", "حرم", "overlay", "خريطة", "geojson", "gis"])

    if wants_dxf and len(points) >= 2:
        crs_label = (file_analysis or {}).get("inferred_units", "Projected Meters")
        artifact = generate_survey_dxf(points=points, crs_label=crs_label)
        engineered_context += f"\n[نتائج محرك AutoCAD DXF الفعلية]:\n{json.dumps(artifact['metrics'], ensure_ascii=False)}\n{artifact['note']}\n"
    elif wants_dxf and len(points) < 2:
        warnings.append("لإنشاء ملف DXF تلقائياً، يرجى إرفاق ملف Excel أو CSV يحتوي على عمودي X و Y لنقطتين على الأقل.")

    if wants_gis and len(points) >= 1 and artifact is None:
        op = "buffer" if ("buffer" in message.lower() or "حرم" in message) else "summary"
        geom_type = "polygon" if len(points) >= 3 else ("line" if len(points) == 2 else "point")
        gdf = points_to_geodataframe(points, geom_type=geom_type)
        artifact = run_spatial_analysis(gdf, operation=op, buffer_meters=100.0)
        engineered_context += f"\n[نتائج محرك GeoPandas GIS الفعلية]:\n{json.dumps(artifact['metrics'], ensure_ascii=False)}\n"

    if not settings.GEMINI_API_KEY:
        fallback_reply = (
            "✅ تمت المعالجة الهندسية بنجاح عبر محركات الخادم (ezdxf / GeoPandas).\n"
            f"{engineered_context}\n"
            "⚠️ ملاحظة التشغيل: لإتاحة الشرح الذكي التفاعلي والمدرس الهندسي، أضف متغير GEMINI_API_KEY في ملف .env على الخادم."
        )
        return {"reply": fallback_reply, "warnings": warnings, "artifact": artifact}

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    full_prompt = f"الوضع النشط: {mode}\nطلب المستخدم: {message}\n"
    if file_analysis:
        safe_meta = {k: v for k, v in file_analysis.items() if k != "image_path"}
        full_prompt += f"\nبيانات الملف المرفوع المُحللة:\n{json.dumps(safe_meta, ensure_ascii=False)[:6000]}\n"
    if engineered_context:
        full_prompt += engineered_context

    contents: List[Any] = [full_prompt]
    if file_analysis and "image_path" in file_analysis:
        contents.append(Image.open(file_analysis["image_path"]))

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_ENGINEERING_PROMPT,
            temperature=0.2,
        ),
    )

    return {
        "reply": response.text or "تمت معالجة الطلب بنجاح.",
        "warnings": warnings,
        "artifact": artifact,
    }
