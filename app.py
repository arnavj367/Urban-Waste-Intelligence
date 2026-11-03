from pathlib import Path
import json, os, re, time
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from src.config import get_setting, has_setting
from src.database import (init_db, create_report, list_reports, list_vehicles, update_report_status,
    add_vehicle, get_report, find_recent_duplicate, update_vehicle, list_activity)
from src.dispatch import assign_vehicle
from src.notifications import send_incident_webhook, build_incident_event
from src.vision import analyze_image
from src.utils import ensure_dirs

ensure_dirs(ROOT)
init_db()
st.set_page_config(page_title="Urban Waste Intelligence | Command Center", page_icon="♻️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--bg:#081310;--panel:#10201c;--panel2:#142923;--line:#24453a;--mint:#65e6b4;--text:#ecf8f2;--muted:#91aaa0}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.stApp{background:radial-gradient(ellipse at 10% 0%,#173c2e 0%,#0b1713 34%,#08110f 100%);color:var(--text)}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0d1c17,#0a1411);border-right:1px solid var(--line)}
.block-container{max-width:1580px;padding-top:1.4rem;padding-bottom:3rem}
.hero{position:relative;overflow:hidden;padding:30px 34px;border:1px solid #31644e;border-radius:24px;background:linear-gradient(115deg,rgba(22,93,65,.94),rgba(13,39,31,.98) 58%,rgba(15,34,30,.96));box-shadow:0 20px 60px #0004;margin-bottom:20px}
.hero:after{content:'♻';position:absolute;right:34px;top:-45px;font-size:210px;color:#b5ffdc12;transform:rotate(-15deg)}
.eyebrow{font-size:.72rem;letter-spacing:2.3px;font-weight:800;color:#8af0c3;text-transform:uppercase;margin-bottom:9px}
.hero h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(2rem,4vw,3.3rem);line-height:1.05;letter-spacing:-1.7px;margin:0;color:#f2fff8;font-weight:700}
.hero p{font-size:1rem;color:#c3e8d5;margin:.7rem 0 0;max-width:760px}
.section-kicker{font-size:.72rem;letter-spacing:1.8px;text-transform:uppercase;color:#80dcb4;font-weight:800;margin-bottom:5px}
.section-title{font-family:'Space Grotesk',sans-serif;font-size:1.55rem;font-weight:700;letter-spacing:-.6px;margin:0 0 14px}
[data-testid="stMetric"]{background:linear-gradient(145deg,#142a22,#10201c);border:1px solid #2a5141;padding:17px 19px;border-radius:17px;box-shadow:0 8px 25px #0002}
[data-testid="stMetricLabel"]{color:#9bb8aa}
[data-testid="stMetricValue"]{color:#f0fff7;font-family:'Space Grotesk',sans-serif;font-weight:700}
.stButton>button,.stFormSubmitButton>button{border-radius:11px;border:1px solid #368966;background:linear-gradient(120deg,#1d7654,#15583f);color:white;font-weight:700;min-height:2.65rem;transition:.18s}
.stButton>button:hover,.stFormSubmitButton>button:hover{border-color:#8af0c3;background:#258a63;color:white;transform:translateY(-1px)}
.stTabs [data-baseweb="tab-list"]{gap:8px;background:#0e1c17;padding:8px;border:1px solid #29483b;border-radius:14px}
.stTabs [data-baseweb="tab"]{border-radius:9px;padding:10px 16px;color:#c2d8cb}
.stTabs [aria-selected="true"]{background:#1e6549;color:white}
section[data-testid="stForm"]{background:#10211b;border:1px solid #2a4a3c;border-radius:16px;padding:20px}
[data-testid="stDataFrame"]{border:1px solid #29483b;border-radius:12px;overflow:hidden}
[data-testid="stAlert"]{border-radius:13px}
hr{border-color:#29483b}
h2,h3{letter-spacing:-.5px}
.small-muted{color:#94ada2;font-size:.85rem}
.panel{background:linear-gradient(145deg,#132720,#0f1e19);border:1px solid #2a4b3d;border-radius:17px;padding:18px 20px}
.pill{display:inline-block;border:1px solid #3b6955;background:#153b2b;color:#baf5d7;padding:4px 10px;border-radius:99px;font-size:.75rem;font-weight:700}
</style>""", unsafe_allow_html=True)


def section(title, kicker=None, subtitle=None):
    if kicker: st.markdown(f'<div class="section-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle: st.caption(subtitle)


def safe_json(value):
    if isinstance(value, dict): return value
    try: return json.loads(value or "{}")
    except Exception: return {}


def status_pill(value):
    colors = {"Critical": "#ff6868", "High": "#ff9c55", "Medium": "#f0c96a", "Low": "#6ed7a0", "Needs Review": "#9ba9b0", "Completed": "#6ed7a0", "In Progress": "#6db9ee", "Assigned": "#9b9cf0"}
    color = colors.get(str(value), "#a9bbb2")
    return f'<span style="display:inline-block;background:{color}1b;color:{color};border:1px solid {color}66;padding:4px 10px;border-radius:30px;font-size:.75rem;font-weight:800">{value}</span>'


def get_data():
    return list_reports(), list_vehicles()


reports, vehicles = get_data()
open_status = ["New", "Assigned", "Accepted", "In Progress", "Needs Review"]
open_reports = reports[reports.status.isin(open_status)] if not reports.empty else reports
critical_count = int(reports.severity.eq("Critical").sum()) if not reports.empty else 0
high_count = int(reports.severity.eq("High").sum()) if not reports.empty else 0
available_count = int(vehicles.status.eq("Available").sum()) if not vehicles.empty else 0

with st.sidebar:
    st.markdown("<div style='font-family:Space Grotesk;font-size:1.5rem;font-weight:700;color:#eafff3'>♻ UWI <span style='color:#6ce5b2'>/ 02</span></div>", unsafe_allow_html=True)
    st.caption("URBAN WASTE INTELLIGENCE")
    st.markdown("<div class='pill'>● COMMAND CENTER</div>", unsafe_allow_html=True)
    st.divider()
    page = st.radio("NAVIGATION", ["Overview", "Report Waste", "Incident Operations", "Fleet Control", "Camera Intelligence", "Integrations"], label_visibility="visible")
    st.divider()
    st.markdown("**SYSTEM HEALTH**")
    st.caption("AI vision")
    if has_setting("GEMINI_API_KEY"): st.success("Connected", icon="🧠")
    else: st.warning("API key required", icon="🧠")
    st.caption("Storage · SQLite")
    st.caption("Dispatch · Nearest available demo fleet")
    st.caption("Notifications · " + ("Webhook configured" if has_setting("UWI_ALERT_WEBHOOK") else "Not configured"))
    st.divider()
    if st.button("↻ Refresh dashboard", use_container_width=True): st.rerun()
    st.caption("V2.0 · Smart city waste operations")

st.markdown("""<div class='hero'><div class='eyebrow'>SMART CITY OPERATIONS · AI-POWERED CIVIC RESPONSE</div><h1>Urban Waste<br>Intelligence.</h1><p>See the problem. Understand its severity. Route the response. One connected command center for cleaner, faster and more accountable waste collection.</p></div>""", unsafe_allow_html=True)

if page == "Overview":
    section("Operations at a glance", "LIVE SITUATION ROOM", "A consolidated view of reported waste, response priorities and collection capacity.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total incidents", len(reports), help="All submitted and camera-generated reports")
    c2.metric("Open incidents", len(open_reports))
    c3.metric("Critical priority", critical_count)
    c4.metric("High priority", high_count)
    c5.metric("Available vehicles", available_count)
    st.write("")
    left,right = st.columns([1.35,.85], gap="large")
    with left:
        section("Incident activity", "RESPONSE QUEUE")
        if reports.empty: st.info("No incidents yet. Submit a waste image to populate the command center.")
        else:
            view = reports.head(8)[["id","created_at","location","severity","status","vehicle_name"]].copy()
            view.columns = ["Incident ID","Reported","Location","Priority","Status","Assigned vehicle"]
            st.dataframe(view, use_container_width=True, hide_index=True)
    with right:
        section("Severity distribution", "AI TRIAGE")
        if reports.empty: st.info("Severity analytics will appear after the first report.")
        else:
            counts = reports.severity.value_counts().reindex(["Critical","High","Medium","Low","Needs Review"], fill_value=0)
            st.bar_chart(counts, height=230)
    st.divider()
    map_col, fleet_col = st.columns([1.2,.8], gap="large")
    with map_col:
        section("Incident map", "GEOGRAPHIC OVERVIEW")
        mapped = reports.dropna(subset=["latitude","longitude"])[["latitude","longitude"]].rename(columns={"latitude":"lat","longitude":"lon"}) if not reports.empty else pd.DataFrame()
        if not mapped.empty: st.map(mapped, use_container_width=True)
        else: st.info("Location pins appear after reports include GPS coordinates.")
    with fleet_col:
        section("Fleet readiness", "COLLECTION CAPACITY")
        if vehicles.empty: st.info("No vehicles registered.")
        else:
            for _,v in vehicles.iterrows():
                st.markdown(f"**{v['name']}** · {v['status']}")
                st.progress(min(1, float(v.active_jobs)/max(1,float(v.capacity))))
                st.caption(f"{int(v.active_jobs)} / {int(v.capacity)} active jobs · {v.collector_name or 'Collector not assigned'}")
    st.divider()
    section("Recent system activity", "AUDIT TRAIL")
    activity = list_activity(8)
    if activity.empty: st.caption("No activity has been recorded yet.")
    else: st.dataframe(activity[["created_at","report_id","action","details"]], use_container_width=True, hide_index=True)

elif page == "Report Waste":
    section("Create a waste incident", "CITIZEN & FIELD REPORTING", "Upload a photo or capture one with your device. AI assesses the visible waste and assigns a priority automatically.")
    left,right = st.columns([1.1,.9], gap="large")
    with left:
        with st.form("report_form_v2", clear_on_submit=True):
            capture = st.camera_input("Capture waste photo")
            upload = st.file_uploader("Or upload an image", type=["jpg","jpeg","png","webp"], help="Maximum 10 MB")
            image = capture if capture is not None else upload
            st.markdown("**Incident details**")
            location = st.text_input("Location / landmark", placeholder="e.g. Near community park, Gate 2")
            reporter = st.text_input("Reported by", placeholder="Name or team (optional)")
            g1,g2 = st.columns(2)
            lat = g1.number_input("Latitude", min_value=-90.0, max_value=90.0, value=26.8467, format="%.6f")
            lon = g2.number_input("Longitude", min_value=-180.0, max_value=180.0, value=80.9462, format="%.6f")
            notes = st.text_area("Additional context", placeholder="Landmark, access restrictions, waste category if known…", height=85)
            allow_duplicate = st.checkbox("Create a new incident even if a nearby open report exists")
            submitted = st.form_submit_button("✦ Analyse image & create incident", type="primary", use_container_width=True)
    with right:
        st.markdown("<div class='panel'><div class='section-kicker'>AUTOMATIC AI TRIAGE</div><h3 style='margin-top:0'>No manual severity selection.</h3><p style='color:#a9c3b7'>The vision model examines the uploaded image, estimates visible waste coverage, identifies waste types and returns a conservative severity classification.</p><hr><b>Assessment outputs</b><ul style='color:#b7cec2;line-height:1.9'><li>Waste presence and visible categories</li><li>Estimated visible coverage</li><li>Low / Medium / High / Critical</li><li>Confidence and visual rationale</li><li>Visible safety or access hazards</li></ul><div class='pill'>Human verification for urgent dispatch</div></div>", unsafe_allow_html=True)
        st.write("")
        st.info("For reliable image analysis, configure GEMINI_API_KEY in Streamlit → App settings → Secrets.")
    if submitted:
        if image is None: st.error("Please capture or upload a photo.")
        elif not location.strip(): st.error("Enter a location or landmark.")
        elif len(image.getvalue()) > 10*1024*1024: st.error("Image exceeds 10 MB.")
        else:
            duplicate = find_recent_duplicate(float(lat),float(lon),50,30)
            if duplicate and not allow_duplicate:
                st.warning(f"Possible duplicate: {duplicate['id']} · {duplicate['location']} · approx. {duplicate['distance_m']} m away. No incident created.")
            else:
                with st.spinner("AI is inspecting the image…"):
                    vision = analyze_image(image.getvalue(), ROOT)
                    severity = vision.get("severity", "Needs Review")
                    rid = create_report(image.getvalue(), ROOT, location.strip(), float(lat), float(lon), reporter.strip() or "Anonymous", notes.strip(), severity, vision)
                    assignment = assign_vehicle(rid) if severity in ("High","Critical") else {"assigned":False,"reason":"Standard priority · queued for operations review."}
                    report_record = get_report(rid)
                    notification = send_incident_webhook(build_incident_event(report_record, assignment)) if severity in ("High","Critical") else {"sent":False,"status":"not_required"}
                st.success(f"Incident created · {rid}")
                a,b,c = st.columns(3)
                a.metric("AI-assessed severity", severity)
                b.metric("Model confidence", f"{vision.get('confidence',0)}%")
                cov = vision.get("estimated_coverage_pct")
                c.metric("Visible waste coverage", f"{cov}%" if cov is not None else "Not estimated")
                r1,r2 = st.columns([.8,1.2])
                with r1: st.image(image, caption="Submitted evidence", use_container_width=True)
                with r2:
                    st.markdown("**AI visual assessment**")
                    st.write(vision.get("summary","No summary returned."))
                    if vision.get("waste_types"): st.write("**Detected:** " + ", ".join(vision["waste_types"]))
                    if vision.get("hazards"): st.warning("Visible concerns: " + ", ".join(vision["hazards"]))
                    if vision.get("rationale"): st.caption(vision["rationale"])
                    if assignment.get("assigned"):
                        st.success(f"Assigned to {assignment['vehicle_name']} · {assignment.get('distance_km','?')} km straight-line distance")
                        if notification.get("sent"): st.success("Incident webhook delivered.")
                        elif notification.get("status") not in ("not_required","not_configured"): st.warning("Webhook delivery: " + notification.get("status","unknown"))
                    else: st.info(assignment.get("reason","Awaiting operations review."))
                    if vision.get("warning"): st.caption(vision["warning"])
                st.caption("Vehicle assignment uses the demo fleet registry. A real truck is not contacted unless you connect an authenticated fleet/notification provider.")

elif page == "Incident Operations":
    section("Incident operations", "DISPATCH & FIELD EXECUTION", "Review incoming incidents, assign resources and track work through completion.")
    if reports.empty: st.info("No incidents to manage yet.")
    else:
        f1,f2,f3 = st.columns(3)
        severity_filter = f1.multiselect("Priority", ["Critical","High","Medium","Low","Needs Review"], default=["Critical","High","Medium","Low","Needs Review"])
        status_filter = f2.multiselect("Status", ["New","Assigned","Accepted","In Progress","Completed","Needs Review"], default=["New","Assigned","Accepted","In Progress","Needs Review"])
        search = f3.text_input("Search location / ID", placeholder="Search…")
        filtered = reports[reports.severity.isin(severity_filter) & reports.status.isin(status_filter)].copy()
        if search.strip(): filtered = filtered[filtered.location.str.contains(search,case=False,na=False) | filtered.id.str.contains(search,case=False,na=False)]
        st.dataframe(filtered[["id","created_at","location","severity","status","vehicle_name"]], use_container_width=True, hide_index=True)
        if not filtered.empty:
            selected = st.selectbox("Open incident", filtered.id.tolist(), format_func=lambda x: f"{x} · {filtered.loc[filtered.id==x,'location'].iloc[0]}")
            item = get_report(selected)
            if item:
                st.divider(); left,right = st.columns([1,1], gap="large")
                with left:
                    st.markdown(f"### {item['location']}")
                    st.markdown(f"{status_pill(item['severity'])} &nbsp; {status_pill(item['status'])}", unsafe_allow_html=True)
                    st.caption(f"{item['id']} · {item['created_at']} · Reported by {item.get('reported_by') or 'Unknown'}")
                    if item.get("image_path") and Path(item["image_path"]).exists(): st.image(item["image_path"], use_container_width=True)
                    if item.get("proof_path") and Path(item["proof_path"]).exists(): st.image(item["proof_path"], caption="Proof of cleaning", use_container_width=True)
                    vision = item.get("vision_json",{})
                    if vision: st.write(vision.get("summary","")); st.caption(vision.get("rationale",""))
                with right:
                    st.markdown("#### Dispatch details")
                    st.write("**Assigned vehicle:** " + str(item.get("vehicle_name") or "Unassigned"))
                    if item.get("latitude") is not None: st.write(f"**Coordinates:** {item['latitude']:.6f}, {item['longitude']:.6f}")
                    statuses = ["New","Assigned","Accepted","In Progress","Completed","Needs Review"]
                    new_status = st.selectbox("Update workflow status", statuses, index=statuses.index(item["status"]) if item["status"] in statuses else 0, key="incident_status")
                    proof = st.file_uploader("Completion proof photo", type=["jpg","jpeg","png","webp"], key="incident_proof")
                    b1,b2 = st.columns(2)
                    if b1.button("Save status", type="primary", use_container_width=True):
                        proof_path = None
                        if proof:
                            proof_dir = ROOT/"uploads"; proof_dir.mkdir(exist_ok=True)
                            proof_path = str(proof_dir/f"proof_{selected}_{int(time.time())}.jpg")
                            proof_dir.joinpath(Path(proof_path).name).write_bytes(proof.getvalue())
                        update_report_status(selected,new_status,proof_path); st.success("Incident updated."); st.rerun()
                    if b2.button("Assign nearest truck", use_container_width=True, disabled=item.get("vehicle_id") is not None):
                        result = assign_vehicle(selected)
                        if result.get("assigned"):
                            refreshed = get_report(selected)
                            delivery = send_incident_webhook(build_incident_event(refreshed,result)) if item["severity"] in ("High","Critical") else {"sent":False}
                            st.success("Assigned: " + result["vehicle_name"])
                            if delivery.get("sent"): st.success("Webhook delivered.")
                        else: st.warning(result.get("reason"))
                        st.rerun()

elif page == "Fleet Control":
    section("Fleet control", "VEHICLE & COLLECTOR MANAGEMENT", "Maintain the demo fleet registry and see where available collection capacity is positioned.")
    if vehicles.empty: st.info("No fleet vehicles registered.")
    else:
        f1,f2,f3 = st.columns(3)
        f1.metric("Registered vehicles",len(vehicles)); f2.metric("Available",int(vehicles.status.eq("Available").sum())); f3.metric("Active assignments",int(vehicles.active_jobs.sum()))
        fleet = vehicles.copy(); fleet["Capacity"] = fleet.apply(lambda r:f"{int(r.active_jobs)} / {int(r.capacity)}",axis=1)
        st.dataframe(fleet[["name","status","Capacity","collector_name","collector_phone","latitude","longitude"]], use_container_width=True, hide_index=True)
        map_df = vehicles.rename(columns={"latitude":"lat","longitude":"lon"})[["lat","lon"]]
        st.map(map_df,use_container_width=True)
        st.markdown("#### Update vehicle availability")
        selected_vehicle = st.selectbox("Vehicle", vehicles.id.tolist(), format_func=lambda x: vehicles.loc[vehicles.id==x,"name"].iloc[0])
        current = vehicles[vehicles.id==selected_vehicle].iloc[0]
        new_vehicle_status = st.selectbox("Operational status",["Available","Busy","Offline"],index=["Available","Busy","Offline"].index(current.status) if current.status in ["Available","Busy","Offline"] else 0)
        if st.button("Save vehicle status"):
            update_vehicle(int(selected_vehicle),status=new_vehicle_status); st.success("Vehicle updated."); st.rerun()
    with st.expander("＋ Register a vehicle / collector"):
        with st.form("add_vehicle_v2"):
            a,b = st.columns(2); name = a.text_input("Vehicle name",placeholder="Truck 05"); capacity = b.number_input("Jobs per shift",1,100,5)
            c,d = st.columns(2); collector = c.text_input("Collector name"); phone = d.text_input("Collector phone (optional)",placeholder="+91…")
            e,f = st.columns(2); vlat = e.number_input("Vehicle latitude",value=26.8467,format="%.6f"); vlon = f.number_input("Vehicle longitude",value=80.9462,format="%.6f")
            if st.form_submit_button("Register vehicle",type="primary"):
                if name.strip(): add_vehicle(name.strip(),float(vlat),float(vlon),int(capacity),collector.strip(),phone.strip()); st.success("Vehicle registered."); st.rerun()
                else: st.error("Vehicle name is required.")
    st.info("Nearest assignment uses straight-line GPS distance and available capacity. It is not live GPS telemetry or road-route optimization. Vehicle data is demo data until connected to a real fleet feed.")

elif page == "Camera Intelligence":
    section("Camera intelligence", "CONTINUOUS SITE MONITORING", "Connect authorized IP cameras through the separate always-on camera worker. The Streamlit page itself does not run a 24/7 process.")
    status_file = ROOT/"data"/"camera_status.json"
    status = {}
    if status_file.exists():
        try: status = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception: status = {}
    heartbeat = status.get("last_heartbeat")
    c1,c2,c3 = st.columns(3)
    c1.metric("AI vision", "Connected" if has_setting("GEMINI_API_KEY") else "Not configured")
    c2.metric("Camera worker", "Running" if heartbeat and time.time()-float(heartbeat)<90 else "Not detected")
    c3.metric("Last assessment", status.get("last_severity","—"))
    if heartbeat:
        st.caption("Last worker heartbeat: " + datetime.fromtimestamp(float(heartbeat)).strftime("%d %b %Y, %H:%M:%S"))
    if status.get("last_error"): st.error("Camera worker: " + str(status["last_error"]))
    if has_setting("UWI_CAMERA_URL"):
        st.success("Camera source configured. Stream URL is hidden for security.")
    else: st.warning("No camera source configured. Set UWI_CAMERA_URL in the worker host environment or .env file.")
    st.markdown("#### Worker launch command")
    st.code("python camera_worker.py", language="bash")
    st.markdown("#### Monitoring pipeline")
    st.code("Authorized RTSP camera → frame sampler → Gemini vision → incident deduplication → nearest available vehicle → signed webhook",language="text")
    st.info("For actual 24/7 monitoring, run camera_worker.py on an always-on machine with network access to the camera. Streamlit Community Cloud generally cannot access a private LAN RTSP camera and is not a background-worker host. Keep camera credentials in environment secrets, not GitHub.")

elif page == "Integrations":
    section("Integrations & deployment", "SYSTEM CONFIGURATION", "Check the integration readiness of the AI provider, outbound webhook and deployment environment.")
    c1,c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Gemini AI vision")
        if has_setting("GEMINI_API_KEY"): st.success("API key detected · " + get_setting("GEMINI_VISION_MODEL","gemini-3.5-flash-lite"))
        else: st.warning("GEMINI_API_KEY is missing.")
        st.code('GEMINI_API_KEY = "your-api-key"\nGEMINI_VISION_MODEL = "gemini-3.5-flash-lite"',language="toml")
        st.caption("Add these values under Streamlit Community Cloud → App settings → Secrets. Never commit keys to GitHub.")
    with c2:
        st.markdown("#### Outbound incident webhook")
        if has_setting("UWI_ALERT_WEBHOOK"): st.success("Webhook endpoint configured · URL hidden")
        else: st.warning("Webhook endpoint not configured.")
        st.caption("Webhook delivery is sent for assigned High/Critical incidents. Optional HMAC signing uses UWI_WEBHOOK_SECRET.")
        st.code('UWI_ALERT_WEBHOOK = "https://your-service.example/uwi"\nUWI_WEBHOOK_SECRET = "use-a-long-random-secret"',language="toml")
        if st.button("Send test webhook",type="primary",disabled=not has_setting("UWI_ALERT_WEBHOOK")):
            sample = {"event":"uwi.integration_test","schema_version":"2.0","message":"Urban Waste Intelligence webhook test","sent_at":datetime.now().astimezone().isoformat()}
            result = send_incident_webhook(sample)
            if result.get("sent"): st.success(f"Webhook delivered · HTTP {result.get('http_status')}")
            else: st.error(result.get("message",result.get("status","Delivery failed")))
    st.divider()
    section("Deployment checklist", "STREAMLIT CLOUD")
    st.markdown("""1. Push the project files to a GitHub repository (exclude `.env`, `.venv`, local database and uploads).\n2. Create a Streamlit Community Cloud app pointing to `app.py`.\n3. Add `GEMINI_API_KEY` and optional webhook settings under **App settings → Secrets**.\n4. Use persistent external storage/database for production; local app storage can be ephemeral.\n5. Deploy the RTSP worker separately on an always-on host; point it to the same persistent database and object storage.\n6. Connect real fleet GPS and collector notification APIs before enabling operational dispatch.""")
    st.download_button("Download current incident register (CSV)", reports.drop(columns=["image_path","vision_json","proof_path"],errors="ignore").to_csv(index=False).encode("utf-8-sig"), "uwi_incidents_v2.csv", "text/csv", use_container_width=True)

st.divider()
st.markdown("<div class='small-muted'>URBAN WASTE INTELLIGENCE · V2.0 · AI visual triage · Simulated fleet dispatch · Human verification required for real-world action</div>", unsafe_allow_html=True)
