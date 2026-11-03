"""Conservative multimodal waste-scene analysis."""
import base64
import json
import requests
from io import BytesIO
from PIL import Image, ImageOps
from src.config import get_setting


def vision_status():
    key = get_setting("GEMINI_API_KEY")
    model = get_setting("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite")
    return f"Gemini connected · {model}" if key else "AI key missing · analysis unavailable"


def normalize_image(image_bytes: bytes, max_side: int = 1600):
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((max_side, max_side))
    out = BytesIO()
    image.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue(), image


def analyze_image(image_bytes: bytes, root=None):
    """Return image-derived severity; never fall back to guessed severity."""
    key = get_setting("GEMINI_API_KEY")
    model = get_setting("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite")
    if not key:
        return {"mode": "unconfigured", "mode_label": "AI vision not configured", "summary": "Image received, but automatic analysis is unavailable because no Gemini API key is configured.", "waste_present": False, "waste_types": [], "detections": [], "waste_score": 0, "severity": "Needs Review", "confidence": 0, "estimated_coverage_pct": None, "warning": "Configure GEMINI_API_KEY in Streamlit secrets to enable automatic image analysis."}
    try:
        normalized, image = normalize_image(image_bytes)
        prompt = """Act as a cautious municipal waste-scene visual triage assistant. Analyze only visible evidence in the image. Determine whether discarded waste/litter is visible; identify visible waste types; estimate percentage of the visible ground/surface occupied by waste; describe pile size (small/medium/large/unknown), spread (localized/spread-out/unknown), and visible access, drainage or sanitation hazards.
Severity rubric: Low = isolated small litter; Medium = several items or a modest localized pile; High = substantial accumulation, widespread litter or obstruction of a public area; Critical = very large accumulation, severe blockage of access/drainage or an obvious urgent hazard. If image is unclear, unrelated, or waste is not visible, use Needs Review. Do not infer hidden waste, exact mass, disease, or facts outside the image. Confidence is confidence in this visual assessment, not a calibrated probability. Return only JSON with keys waste_present (boolean), waste_types (array), summary (string), coverage_pct (number 0-100 or null), pile_size, spread, severity (Low|Medium|High|Critical|Needs Review), confidence (integer 0-100), hazards (array), rationale (string). Be conservative."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(normalized).decode("ascii")}}]}], "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}
        response = requests.post(endpoint, json=payload, timeout=50)
        response.raise_for_status()
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
        allowed = {"Low", "Medium", "High", "Critical", "Needs Review"}
        severity = data.get("severity") if data.get("severity") in allowed else "Needs Review"
        confidence = max(0, min(100, int(data.get("confidence", 0))))
        coverage = data.get("coverage_pct")
        if coverage is not None:
            coverage = max(0, min(100, float(coverage)))
        waste_types = [str(x)[:80] for x in data.get("waste_types", [])[:12]]
        return {"mode": "gemini", "mode_label": f"Gemini Vision · {model}", "summary": str(data.get("summary", "Image analyzed."))[:1200], "waste_present": bool(data.get("waste_present", False)), "waste_types": waste_types, "detections": [{"label": x, "confidence": None} for x in waste_types], "waste_score": confidence / 100, "severity": severity, "confidence": confidence, "estimated_coverage_pct": coverage, "pile_size": str(data.get("pile_size", "unknown")), "spread": str(data.get("spread", "unknown")), "hazards": [str(x)[:120] for x in data.get("hazards", [])[:10]], "rationale": str(data.get("rationale", ""))[:1200], "warning": "AI visual triage is an estimate. A human operator should verify High/Critical incidents before real-world dispatch."}
    except Exception as exc:
        return {"mode": "error", "mode_label": "AI analysis unavailable", "summary": "The image could not be reliably analyzed. It has been placed in the manual review queue.", "waste_present": False, "waste_types": [], "detections": [], "waste_score": 0, "severity": "Needs Review", "confidence": 0, "estimated_coverage_pct": None, "warning": f"Vision provider error: {str(exc)[:220]}"}
