import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import ezdxf
import pandas as pd
import pdfplumber
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.core.config import settings

ALLOWED_EXT = {".xlsx", ".xls", ".csv", ".pdf", ".dxf", ".geojson", ".json", ".png", ".jpg", ".jpeg", ".webp"}

EASTING_ALIASES = {"x", "e", "easting", "east", "lon", "longitude", "شرق", "شرقيات", "س"}
NORTHING_ALIASES = {"y", "n", "northing", "north", "lat", "latitude", "شمال", "شماليات", "ص"}
ELEVATION_ALIASES = {"z", "elev", "elevation", "rl", "height", "منسوب", "الارتفاع", "ع"}
ID_ALIASES = {"id", "pt", "point", "point_id", "name", "رقم", "النقطة", "كود"}


def sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename)
    clean = re.sub(r"[^a-zA-Z0-9._\-\u0600-\u06FF]", "_", base)
    return f"{uuid.uuid4().hex[:10]}_{clean}"


async def save_and_validate_upload(file: UploadFile, max_mb: int) -> Tuple[Path, str]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"امتداد الملف غير مسموح به: {ext}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="الملف المرفوع فارغ.")
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"حجم الملف يتجاوز الحد الأقصى لباقتك ({max_mb} MB).")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_name = sanitize_filename(file.filename or f"upload{ext}")
    dest_path = Path(settings.UPLOAD_DIR) / safe_name

    with open(dest_path, "wb") as f:
        f.write(content)
    os.chmod(dest_path, 0o640)

    return dest_path, ext


def detect_coordinate_columns(df: pd.DataFrame) -> Dict[str, str]:
    mapping = {}
    for col in df.columns:
        norm = str(col).strip().lower()
        if norm in EASTING_ALIASES and "x" not in mapping:
            mapping["x"] = col
        elif norm in NORTHING_ALIASES and "y" not in mapping:
            mapping["y"] = col
        elif norm in ELEVATION_ALIASES and "z" not in mapping:
            mapping["z"] = col
        elif norm in ID_ALIASES and "id" not in mapping:
            mapping["id"] = col
    return mapping


def analyze_uploaded_file(file_path: Path, ext: str) -> Dict[str, Any]:
    warnings: List[str] = []
    result: Dict[str, Any] = {"file_type": ext, "warnings": warnings}

    if ext in {".xlsx", ".xls", ".csv"}:
        df = pd.read_csv(file_path) if ext == ".csv" else pd.read_excel(file_path)
        df = df.dropna(how="all")
        if df.empty:
            warnings.append("الجدول لا يحتوي على صفوف بيانات صالحة.")
            return result

        col_map = detect_coordinate_columns(df)
        result["columns"] = list(df.columns)
        result["detected_mapping"] = col_map
        result["row_count"] = len(df)

        if "x" not in col_map or "y" not in col_map:
            warnings.append(
                f"لم يتم التعرف تلقائياً على أعمدة الإحداثيات (X/Easting, Y/Northing) من الأعمدة الموجودة: {list(df.columns)}. يرجى تحديد أسماء الأعمدة بوضوح."
            )
            result["preview_rows"] = df.head(10).to_dict(orient="records")
            return result

        x_series = pd.to_numeric(df[col_map["x"]], errors="coerce")
        y_series = pd.to_numeric(df[col_map["y"]], errors="coerce")
        invalid_mask = x_series.isna() | y_series.isna()
        if invalid_mask.any():
            bad_rows = (df.index[invalid_mask] + 2).tolist()
            warnings.append(f"تم استبعاد {invalid_mask.sum()} صف/صفوف لوجود قيم غير رقمية أو فارغة في الإحداثيات (صفوف رقم: {bad_rows}).")

        clean_df = df[~invalid_mask].copy()
        points = []
        for idx, row in clean_df.iterrows():
            pt = {
                "id": str(row[col_map["id"]]) if "id" in col_map and pd.notna(row[col_map["id"]]) else f"P{len(points)+1}",
                "x": float(row[col_map["x"]]),
                "y": float(row[col_map["y"]]),
            }
            if "z" in col_map and pd.notna(row[col_map["z"]]):
                pt["z"] = float(row[col_map["z"]])
            points.append(pt)

        xs = [p["x"] for p in points]
        ys = [p["y"] for p in points]
        if xs and all(-180 <= x <= 180 for x in xs) and all(-90 <= y <= 90 for y in ys):
            result["inferred_units"] = "Degrees (Geographic WGS84 / Lat-Lon)"
            warnings.append("الإحداثيات تقع ضمن نطاق الدرجات الجغرافية (-180..180, -90..90). سيتم إسقاطها إلى UTM بالمتر عند الحساب.")
        else:
            result["inferred_units"] = "Meters (Projected Grid Coordinates)"

        result["points"] = points

    elif ext == ".dxf":
        doc = ezdxf.readfile(str(file_path))
        msp = doc.modelspace()
        layers = [layer.dxf.name for layer in doc.layers]
        entity_counts: Dict[str, int] = {}
        for entity in msp:
            etype = entity.dxftype()
            entity_counts[etype] = entity_counts.get(etype, 0) + 1
        result["dxf_version"] = doc.dxfversion
        result["layers"] = layers
        result["entity_counts"] = entity_counts

    elif ext == ".pdf":
        texts = []
        tables = []
        with pdfplumber.open(str(file_path)) as pdf:
            result["page_count"] = len(pdf.pages)
            for i, page in enumerate(pdf.pages[:15], start=1):
                txt = page.extract_text() or ""
                if txt.strip():
                    texts.append(f"--- صفحة {i} ---\n{txt[:1500]}")
                extracted_tables = page.extract_tables()
                if extracted_tables:
                    tables.extend(extracted_tables[:2])
        result["extracted_text"] = "\n".join(texts)
        result["extracted_tables_sample"] = tables[:3]

    elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
        with Image.open(file_path) as img:
            img.verify()
        with Image.open(file_path) as img:
            result["image_dimensions"] = f"{img.width}x{img.height}"
            result["image_mode"] = img.mode
            result["image_path"] = str(file_path)

    elif ext in {".geojson", ".json"}:
        result["geojson_path"] = str(file_path)

    return result
