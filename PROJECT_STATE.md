# Project State — Urban Waste Intelligence V2

## Current architecture
- Streamlit command-center UI in `app.py`.
- Gemini multimodal image analysis in `src/vision.py`.
- SQLite persistence and audit activity in `src/database.py`.
- Nearest available demo vehicle assignment in `src/dispatch.py`.
- HTTPS webhook + optional HMAC signature in `src/notifications.py`.
- Separate RTSP worker in `camera_worker.py` with reconnect, frame sampling and heartbeat.

## Current capabilities
- Automatic image-derived severity; no user-entered severity.
- Incident submission, duplicate proximity check, operational statuses and proof photo.
- Fleet registry, collector contact fields and capacity status.
- Dashboard KPIs, severity chart, incident/fleet maps and audit trail.
- Camera worker status panel and webhook integration test.

## Important boundaries
- Gemini severity is an estimate and urgent dispatch requires human verification.
- Fleet coordinates are demo data; road routing and live GPS are not integrated.
- Webhook delivery is not a WhatsApp/SMS provider. The receiver must implement actual collector notifications.
- RTSP worker must run on an always-on host with access to the camera network.
- Production deployment needs persistent managed storage, authentication, role controls and audit retention.
