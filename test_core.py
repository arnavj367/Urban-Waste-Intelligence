import os, tempfile, unittest
from pathlib import Path
_tmp = tempfile.TemporaryDirectory()
os.environ["UWI_DB_PATH"] = str(Path(_tmp.name) / "test.db")
from src.database import init_db, create_report, find_recent_duplicate, get_report, update_report_status, list_vehicles
from src.dispatch import assign_vehicle

class CoreWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): init_db()

    def make_report(self, lat=26.8467, lon=80.9462):
        return create_report(b"not-a-real-image", Path(_tmp.name), "Test park", lat, lon, "tester", "", "High", {"mode":"test"})

    def test_duplicate_within_radius_and_time(self):
        rid = self.make_report(26.8000,80.9000)
        duplicate = find_recent_duplicate(26.8001,80.9000,50,30)
        self.assertIsNotNone(duplicate); self.assertEqual(duplicate["id"],rid)
        self.assertIsNone(find_recent_duplicate(27.2,81.2,50,30))

    def test_assignment_and_completion_releases_capacity(self):
        rid = self.make_report()
        result = assign_vehicle(rid)
        self.assertTrue(result["assigned"])
        self.assertEqual(get_report(rid)["status"],"Assigned")
        vehicle_id = get_report(rid)["vehicle_id"]
        before = list_vehicles().set_index("id").loc[vehicle_id,"active_jobs"]
        update_report_status(rid,"Completed")
        after = list_vehicles().set_index("id").loc[vehicle_id,"active_jobs"]
        self.assertEqual(int(after),int(before)-1)

    def test_assignment_is_not_duplicated(self):
        rid = self.make_report()
        self.assertTrue(assign_vehicle(rid)["assigned"])
        self.assertFalse(assign_vehicle(rid)["assigned"])

    def test_needs_coordinates_to_assign(self):
        rid = create_report(b"x",Path(_tmp.name),"No GPS",None,None,"tester","","Critical",{})
        self.assertFalse(assign_vehicle(rid)["assigned"])

if __name__ == "__main__": unittest.main(verbosity=2)
