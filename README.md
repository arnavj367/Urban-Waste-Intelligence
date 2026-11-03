# Urban Waste Intelligence — V2 Command Center

A Streamlit smart-waste operations prototype with automatic image-based waste severity assessment, incident operations, fleet registry, a separate RTSP camera worker, and signed outbound webhook notifications.

## V2 highlights

- **Command-center dashboard:** incident KPIs, severity distribution, incident map, fleet readiness and activity trail.
- **Automatic image triage:** Gemini multimodal vision identifies visible waste, estimates visible coverage, classifies severity and records confidence/rationale. There is no manual severity selector.
- **Incident workflow:** duplicate proximity check, incident register, filters, assignment, status tracking and proof-of-cleaning upload.
- **Fleet control:** register demo vehicles and collector contacts, track capacity and availability, and assign the nearest available vehicle using straight-line distance.
- **Camera intelligence:** separate always-on RTSP worker with reconnect logic, frame sampling, deduplication, confidence threshold and heartbeat status.
- **Webhook notifications:** HTTPS POST, optional HMAC-SHA256 signature, timeout and retry behavior. High/Critical assigned incidents can be sent from citizen reporting or the camera worker.
- **Audit trail:** records report creation, assignment and status updates.

## Run locally (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
streamlit run app.py
```

Open `http://localhost:8501`.

Get a Gemini API key from Google AI Studio. For Streamlit Community Cloud, add the following under **App → Settings → Secrets**:

```toml
GEMINI_API_KEY = "your-key"
GEMINI_VISION_MODEL = "gemini-3.5-flash-lite"
```

If the key is missing or the provider fails, the system marks the incident `Needs Review`; it does not guess a severity.

## RTSP camera worker

1. Use an authorized IP camera/NVR with RTSP enabled. Create a dedicated read-only account.
2. Test the stream in VLC before configuring the application.
3. Copy `.env.example` to `.env` and set `UWI_CAMERA_URL`, camera location and GPS coordinates.
4. Install camera dependencies:

```powershell
pip install -r requirements-vision.txt
```

5. Start the worker in a separate terminal:

```powershell
python camera_worker.py
```

The worker samples a frame every `UWI_FRAME_INTERVAL_SECONDS`, sends it to Gemini vision, deduplicates nearby incidents, and creates High/Critical incidents only when the configured confidence threshold is met. The worker reconnects when the camera stream drops and writes a heartbeat to `data/camera_status.json`.

**24/7 requirement:** run this worker on an always-on host with network access to the camera. Streamlit Community Cloud is not an always-on RTSP worker and generally cannot access private LAN camera streams. Use a VPN/private network for remote camera access; do not expose camera ports publicly.

## Webhook setup

Set these in `.env` for local worker execution, or Streamlit Secrets for app-originated notifications:

```toml
UWI_ALERT_WEBHOOK = "https://your-service.example/uwi"
UWI_WEBHOOK_SECRET = "a-long-random-secret"
```

The request is a JSON `POST`. When a secret is configured, the request includes `X-UWI-Signature: sha256=<hex HMAC-SHA256 of the exact request body>`. Your receiver should verify this signature before processing the event. The Integrations page includes a test webhook button.

Example event:

```json
{
  "event": "waste_incident",
  "schema_version": "2.0",
  "report_id": "UWI-1234ABCD",
  "severity": "Critical",
  "location": "Main Street Monitoring Point",
  "latitude": 26.8467,
  "longitude": 80.9462,
  "analysis": "Large accumulation of mixed waste visible.",
  "confidence": 91,
  "assignment": {
    "assigned": true,
    "vehicle_name": "Truck 01",
    "collector_phone": "+91..."
  }
}
```

The webhook is only a transport mechanism. To send WhatsApp/SMS/push alerts, your receiving service must connect to an authorized provider and map the assigned collector to a verified contact. Never place provider tokens in GitHub.

## Deploy the dashboard with Streamlit Community Cloud

Upload/push these project items to GitHub:

- `app.py`
- `src/` (all Python modules)
- `requirements.txt`
- `.streamlit/config.toml`
- `README.md`
- `runtime.txt` (if supported by the selected build environment)

Optional worker files (`camera_worker.py`, `requirements-vision.txt`, `.env.example`) can remain in the repository if you plan to deploy the camera worker separately. Do **not** upload `.env`, `.venv`, `data/`, `uploads/`, camera passwords, API keys or `secrets.toml`.

In Streamlit Community Cloud, choose the repository and set the main file path to `app.py`. Add the Gemini and webhook values under App Settings → Secrets.

## Important production limitations

- Severity is an AI visual estimate, not a certified measurement or guarantee. Validate on representative local images and retain human approval before real-world dispatch.
- The included fleet registry is demo data. Nearest assignment uses straight-line GPS distance, not road routing, traffic, or live GPS telemetry.
- A webhook does not itself contact a truck. Connect an authenticated fleet/notification backend and require collector acknowledgement.
- Streamlit Community Cloud's local filesystem may be ephemeral. Use managed persistent database and object storage for production, and configure the dashboard and worker to share them.
- Implement authentication/roles, retention controls, access logging, webhook receiver verification, backups and authorized camera use before public deployment.

## Tests

```powershell
python -m unittest discover -s . -p "test_core.py" -v
```

### App/worker storage topology note

The current V2 persistence adapter is SQLite plus local image files. For this prototype, the Streamlit app and `camera_worker.py` must share the same persistent filesystem and the same `UWI_DB_PATH` so incidents and camera heartbeat data are visible to both. A Streamlit Community Cloud instance does not share its local disk with a worker running elsewhere. If you deploy the dashboard to Community Cloud and the worker to a separate VM, first replace the SQLite/local-file adapter with a shared managed database and object storage; simply copying the same SQLite path into two different hosts will not synchronize data.
