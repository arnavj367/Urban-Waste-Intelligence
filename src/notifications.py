"""Secure outbound incident webhook notifications."""
import hashlib
import hmac
import json
import time
import requests
from src.config import get_setting


def send_incident_webhook(record: dict) -> dict:
    """Send a signed JSON incident event. Returns status without leaking secrets."""
    url = get_setting("UWI_ALERT_WEBHOOK", "").strip()
    if not url:
        return {"sent": False, "status": "not_configured", "message": "No webhook endpoint configured."}
    if not url.lower().startswith("https://") and not url.startswith("http://localhost") and not url.startswith("http://127.0.0.1"):
        return {"sent": False, "status": "blocked", "message": "Webhook must use HTTPS outside localhost."}
    secret = get_setting("UWI_WEBHOOK_SECRET", "")
    body = json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "UrbanWasteIntelligence/2.0"}
    if secret:
        headers["X-UWI-Signature"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    last_error = "Unknown delivery error"
    for attempt in range(3):
        try:
            response = requests.post(url, data=body, headers=headers, timeout=12)
            response.raise_for_status()
            return {"sent": True, "status": "delivered", "http_status": response.status_code, "attempt": attempt + 1}
        except requests.RequestException as exc:
            last_error = str(exc)[:220]
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    return {"sent": False, "status": "failed", "message": last_error}


def build_incident_event(report: dict, assignment: dict) -> dict:
    vision = report.get("vision_json") or {}
    if isinstance(vision, str):
        try:
            vision = json.loads(vision)
        except Exception:
            vision = {}
    return {
        "event": "waste_incident",
        "schema_version": "2.0",
        "report_id": report.get("id"),
        "severity": report.get("severity"),
        "status": report.get("status"),
        "location": report.get("location"),
        "latitude": report.get("latitude"),
        "longitude": report.get("longitude"),
        "analysis": vision.get("summary", ""),
        "confidence": vision.get("confidence", 0),
        "waste_types": vision.get("waste_types", []),
        "assignment": assignment,
    }
