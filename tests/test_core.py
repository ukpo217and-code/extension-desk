import os, tempfile, unittest
os.environ["EXTENSION_DESK_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from extension_desk import core

def rf(h):  # evidence id for the household's zone, 14-day window
    return core.check_weather_and_pest_evidence(h)["rainfall"]["evidence_id"]

class Tools(unittest.TestCase):
    def test_unknown_household(self):
        self.assertIn("error", core.get_farm_context("HH-999"))
    def test_context_stage(self):
        c = core.get_farm_context("HH-001")
        self.assertEqual(c["days_after_planting"], 40); self.assertEqual(c["growth_stage_indicative"], "tasseling/silking")
    def test_missing_rain_not_zero(self):
        e = core.check_weather_and_pest_evidence("HH-007")
        self.assertLess(e["rainfall"]["coverage"], 0.7); self.assertTrue(e["rainfall"]["missing_dates"])
    def test_conflict_flagged(self):
        self.assertTrue(core.check_weather_and_pest_evidence("HH-001")["conflicts"])
    def test_unclear_location_excluded(self):
        e = core.check_weather_and_pest_evidence("HH-001")
        self.assertEqual([x["report_id"] for x in e["excluded_reports"]], ["PR-005"])
    def test_unsourced_rejected(self):
        d = core.draft_advisory_for_review("HH-001", [{"action": "a", "rationale": "b", "evidence_ids": [], "confidence": "low"}], "m", [])
        self.assertEqual(d["error"], "draft rejected")
    def test_fake_evidence_rejected(self):
        d = core.draft_advisory_for_review("HH-001", [{"action": "a", "rationale": "b", "evidence_ids": ["PR-099"], "confidence": "low"}], "m", [])
        self.assertIn("error", d)
    def test_other_cluster_evidence_rejected(self):
        d = core.draft_advisory_for_review("HH-001", [{"action": "a", "rationale": "b", "evidence_ids": ["PR-004"], "confidence": "low"}], "m", [])
        self.assertIn("error", d)
    def test_overconfident_on_thin_rain_rejected(self):
        d = core.draft_advisory_for_review("HH-007", [{"action": "a", "rationale": "b", "evidence_ids": [rf("HH-007")], "confidence": "high"}], "m", [])
        self.assertIn("error", d)
    def test_long_message_rejected(self):
        d = core.draft_advisory_for_review("HH-001", [{"action": "a", "rationale": "b", "evidence_ids": ["HH:HH-001"], "confidence": "low"}], "x" * 321, [])
        self.assertIn("error", d)
    def test_full_gate(self):
        d = core.draft_advisory_for_review("HH-002", [{"action": "Scout for armyworm", "rationale": "verified report", "evidence_ids": ["PR-001"], "confidence": "medium"}], "Scout maize whorls this week.", [])
        self.assertEqual(d["status"], "pending_submission")
        self.assertIn("error", core.officer_decision(d["draft_id"], "Officer A", True))        # cannot approve before submission
        core.submit_for_approval(d["draft_id"])
        self.assertIn("error", core.officer_decision(d["draft_id"], "  ", True))                # named officer required
        self.assertEqual(core.officer_decision(d["draft_id"], "Officer A", True)["status"], "approved")
        with core._conn() as c:
            row = c.execute("SELECT sent FROM outbox WHERE draft_id=?", (d["draft_id"],)).fetchone()
        self.assertEqual(row["sent"], 0)                                                          # never actually sent
    def test_audit_written(self):
        core.get_farm_context("HH-003")
        with core._conn() as c:
            self.assertGreater(c.execute("SELECT COUNT(*) FROM audit_log WHERE tool='get_farm_context'").fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
