"""SQLite persistence layer with safe schema upgrades."""
from pathlib import Path
import json, os, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("UWI_DB_PATH", str(ROOT / "data" / "uwi.db")))


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=25)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, location TEXT NOT NULL,
            latitude REAL, longitude REAL, reported_by TEXT, notes TEXT,
            severity TEXT NOT NULL, status TEXT NOT NULL, image_path TEXT,
            vision_json TEXT, vehicle_id INTEGER, proof_path TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL, capacity INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Available', active_jobs INTEGER NOT NULL DEFAULT 0,
            collector_name TEXT DEFAULT '', collector_phone TEXT DEFAULT '')""")
        cols = {r[1] for r in con.execute("PRAGMA table_info(vehicles)")}
        for name, typ in [("collector_name", "TEXT DEFAULT ''"), ("collector_phone", "TEXT DEFAULT ''")]:
            if name not in cols: con.execute(f"ALTER TABLE vehicles ADD COLUMN {name} {typ}")
        con.execute("CREATE TABLE IF NOT EXISTS activity_log (id INTEGER PRIMARY KEY AUTOINCREMENT, report_id TEXT, action TEXT NOT NULL, details TEXT, created_at TEXT NOT NULL)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")
        if con.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
            con.executemany("INSERT INTO vehicles(name,latitude,longitude,capacity,status,active_jobs) VALUES(?,?,?,?,?,?)", [
                ("Truck 01", 26.8467, 80.9462, 5, "Available", 0), ("Truck 02", 26.8540, 80.9390, 5, "Available", 0),
                ("Truck 03", 26.8380, 80.9550, 4, "Available", 0), ("Mini Van 01", 26.8600, 80.9500, 3, "Available", 0)])


def log_activity(report_id, action, details=""):
    with connect() as con:
        con.execute("INSERT INTO activity_log(report_id,action,details,created_at) VALUES(?,?,?,?)", (report_id, action, details, datetime.now().astimezone().isoformat(timespec="seconds")))


def list_activity(limit=30):
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", con, params=(limit,))


def find_recent_duplicate(latitude, longitude, within_m=50, within_minutes=30):
    from src.dispatch import haversine_km
    cutoff = (datetime.now().astimezone() - timedelta(minutes=within_minutes)).isoformat(timespec="seconds")
    with connect() as con:
        rows = con.execute("SELECT id,created_at,location,severity,status,latitude,longitude FROM reports WHERE created_at>=? AND status!='Completed'", (cutoff,)).fetchall()
    matches = []
    for row in rows:
        if row["latitude"] is None or row["longitude"] is None: continue
        distance = haversine_km(float(latitude), float(longitude), float(row["latitude"]), float(row["longitude"])) * 1000
        if distance <= within_m: matches.append((distance, dict(row)))
    if not matches: return None
    distance, record = min(matches, key=lambda x: x[0])
    return record | {"distance_m": round(distance, 1)}


def create_report(image_bytes, root, location, latitude, longitude, reported_by, notes, severity, vision_result):
    from src.vision import normalize_image
    report_id = "UWI-" + uuid.uuid4().hex[:8].upper()
    upload_dir = Path(root) / "uploads"; upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        normalized, _ = normalize_image(image_bytes)
    except Exception:
        normalized = image_bytes
    image_path = upload_dir / f"{report_id}.jpg"; image_path.write_bytes(normalized)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connect() as con:
        con.execute("""INSERT INTO reports(id,created_at,location,latitude,longitude,reported_by,notes,severity,status,image_path,vision_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (report_id, now, location, latitude, longitude, reported_by, notes, severity, "New", str(image_path), json.dumps(vision_result)))
    log_activity(report_id, "Report created", f"Severity: {severity} · Location: {location}")
    return report_id


def list_reports():
    with connect() as con:
        return pd.read_sql_query("""SELECT r.id,r.created_at,r.location,r.latitude,r.longitude,r.reported_by,r.notes,r.severity,r.status,
        v.name AS vehicle_name,r.image_path,r.vision_json,r.proof_path FROM reports r LEFT JOIN vehicles v ON r.vehicle_id=v.id ORDER BY r.created_at DESC""", con)


def list_vehicles():
    with connect() as con:
        return pd.read_sql_query("SELECT id,name,latitude,longitude,capacity,status,active_jobs,collector_name,collector_phone FROM vehicles ORDER BY id", con)


def get_report(report_id):
    with connect() as con:
        row = con.execute("SELECT r.*,v.name AS vehicle_name,v.collector_name,v.collector_phone FROM reports r LEFT JOIN vehicles v ON r.vehicle_id=v.id WHERE r.id=?", (report_id,)).fetchone()
        if not row: return None
        result = dict(row)
        try: result["vision_json"] = json.loads(result.get("vision_json") or "{}")
        except Exception: result["vision_json"] = {}
        return result


def update_report_status(report_id, status, proof_path=None):
    allowed = {"New", "Assigned", "Accepted", "In Progress", "Completed", "Needs Review"}
    if status not in allowed: raise ValueError("Invalid status")
    with connect() as con:
        row = con.execute("SELECT status,vehicle_id FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None: return False
        old, vid = row["status"], row["vehicle_id"]
        if proof_path: con.execute("UPDATE reports SET status=?,proof_path=? WHERE id=?", (status, proof_path, report_id))
        else: con.execute("UPDATE reports SET status=? WHERE id=?", (status, report_id))
        if vid is not None and old != status:
            delta = (1 if old == "Completed" and status != "Completed" else -1 if old != "Completed" and status == "Completed" else 0)
            if delta:
                con.execute("UPDATE vehicles SET active_jobs=MAX(0,active_jobs+?),status=CASE WHEN MAX(0,active_jobs+?)>=capacity THEN 'Busy' ELSE 'Available' END WHERE id=?", (delta, delta, vid))
    log_activity(report_id, "Status updated", f"{old} → {status}")
    return True


def add_vehicle(name, latitude, longitude, capacity, collector_name="", collector_phone=""):
    with connect() as con:
        con.execute("INSERT INTO vehicles(name,latitude,longitude,capacity,status,active_jobs,collector_name,collector_phone) VALUES(?,?,?,?, 'Available',0,?,?)", (name, latitude, longitude, capacity, collector_name, collector_phone))


def set_assignment(report_id, vehicle_id):
    with connect() as con:
        cur = con.execute("UPDATE reports SET vehicle_id=?,status='Assigned' WHERE id=? AND vehicle_id IS NULL AND status!='Completed'", (vehicle_id, report_id))
        if cur.rowcount != 1: return False
        cur = con.execute("UPDATE vehicles SET active_jobs=active_jobs+1,status=CASE WHEN active_jobs+1>=capacity THEN 'Busy' ELSE 'Available' END WHERE id=? AND active_jobs<capacity AND status='Available'", (vehicle_id,))
        if cur.rowcount != 1:
            con.execute("UPDATE reports SET vehicle_id=NULL,status='New' WHERE id=?", (report_id,)); return False
    log_activity(report_id, "Vehicle assigned", f"Vehicle ID: {vehicle_id}")
    return True


def update_vehicle(vehicle_id, status=None, latitude=None, longitude=None):
    fields, values = [], []
    if status is not None:
        if status not in {"Available", "Busy", "Offline"}: raise ValueError("Invalid vehicle status")
        fields.append("status=?"); values.append(status)
    if latitude is not None: fields.append("latitude=?"); values.append(latitude)
    if longitude is not None: fields.append("longitude=?"); values.append(longitude)
    if not fields: return
    values.append(vehicle_id)
    with connect() as con: con.execute(f"UPDATE vehicles SET {','.join(fields)} WHERE id=?", values)
