# Geo Surveying AI – حزمة التكامل الكاملة لمنصة أكاديمية جيو مساحة (GeoMasaha Pro)

## محتويات الحزمة
1. **`frontend/`**:
   - `index-ai-snippet.html`: كود زر التبويب وقسم `Geo Surveying AI` الجاهز للإضافة داخل `index.html` دون المساس بأي قسم قائم.
   - `geomasaha-ai.js`: وحدة JavaScript مستقلة لإدارة المحادثة، رفع الملفات، المعاينة الهندسية الفورية لملفات DXF وخرائط Leaflet، وسجل الجلسات.
2. **`geomasaha-ai-backend/`**:
   - خادم **Python FastAPI** متكامل يضم محرك **AutoCAD DXF (`ezdxf`)**، ومحرك **GIS (`GeoPandas + Shapely + PyProj`)**، والحاسبة المساحية الدقيقة، ومنسق **Gemini AI** المؤمّن.

## خطوات التشغيل السريعة
### 1. تشغيل الخادم الخلفي (Backend)
```bash
cd geomasaha-ai-backend
python -m venv venv
source venv/bin/activate  # أو venv\Scripts\activate على ويندوز
pip install -r requirements.txt
cp .env.example .env
# ضع مفتاح GEMINI_API_KEY داخل ملف .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. الربط مع الواجهة الأمامية (GitHub Pages)
1. ارفع ملف `geomasaha-ai.js` إلى مجلد الموقع الرئيسي بجانب `index.html`.
2. أضف محتوى `index-ai-snippet.html` في الأماكن الموضحة داخل `index.html`.
3. عرّف رابط الخادم المنشور قبل استدعاء السكربت:
```html
<script>window.GEOMASAHA_AI_API = "https://your-backend-domain.com/api/v1";</script>
```
