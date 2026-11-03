"""Nearest available vehicle assignment using straight-line distance."""
import math
from src.database import connect, get_report, set_assignment


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * radius * math.asin(min(1, math.sqrt(a)))


def assign_vehicle(report_id):
    report = get_report(report_id)
    if not report: return {"assigned": False, "reason": "Report not found."}
    if report.get("vehicle_id") is not None: return {"assigned": False, "reason": f"Already assigned to {report.get('vehicle_name') or 'a vehicle'}."}
    if report.get("latitude") is None or report.get("longitude") is None: return {"assigned": False, "reason": "Incident coordinates are required for nearest-vehicle assignment."}
    with connect() as con:
        rows = con.execute("SELECT * FROM vehicles WHERE status='Available' AND active_jobs<capacity").fetchall()
    if not rows: return {"assigned": False, "reason": "No available vehicle with remaining capacity. Incident remains in the unassigned queue."}
    ranked = sorted(((haversine_km(report["latitude"], report["longitude"], v["latitude"], v["longitude"]), v["active_jobs"], v) for v in rows), key=lambda x: (x[0], x[1]))
    for distance, _, vehicle in ranked:
        if set_assignment(report_id, vehicle["id"]):
            return {"assigned": True, "vehicle_id": vehicle["id"], "vehicle_name": vehicle["name"], "collector_name": vehicle["collector_name"], "collector_phone": vehicle["collector_phone"], "distance_km": round(distance, 2), "reason": f"Nearest available vehicle · approx. {distance:.2f} km straight-line distance."}
    return {"assigned": False, "reason": "Vehicle capacity changed during assignment. Retry from the operations queue."}
