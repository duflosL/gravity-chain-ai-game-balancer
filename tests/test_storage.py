from concurrent.futures import ThreadPoolExecutor
import csv
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from balancer.analytics import analyze, load_csv
from balancer.storage import Store, export_html, export_recommendations


class StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "reviews.sqlite3"
        self.store = Store(self.path)
        data = b"session_id,level,success,attempts\nprivate-player-id,<script>,1,2\n"
        frame, warnings = load_csv(data)
        self.analysis_id = self.store.save_analysis("=Formule", True, analyze(frame), warnings)
        self.agent = {
            "model": "qwen3:8b",
            "summary": "Limiter l'amplitude des variations.",
            "recommendations": [
                {"id": "rec-1", "level": "<script>", "problem": "Tester", "proposal": "@Intérieur",
                 "rationale": "+preuve", "confidence": "limitée", "indicators": ["n"], "status": "pending"},
                {"id": "rec-2", "level": "<script>", "problem": "Comparer", "proposal": "Contrôler",
                 "rationale": "Confirmer", "confidence": "limitée", "indicators": [], "status": "pending"},
            ],
        }

    def test_round_trip_decisions_and_duplicate_review(self):
        self.assertIsNone(self.store.get_analysis(self.analysis_id)["agent"])
        self.store.save_agent(self.analysis_id, self.agent)
        self.store.set_status(self.analysis_id, "rec-1", "accepted")
        self.store.set_status(self.analysis_id, "rec-2", "rejected")
        with self.assertRaises(ValueError):
            self.store.save_agent(self.analysis_id, self.agent)
        fresh = Store(self.path)
        record = fresh.get_analysis(self.analysis_id)
        self.assertEqual(fresh.list_analyses(), [record])
        self.assertEqual([r["status"] for r in record["agent"]["recommendations"]], ["accepted", "rejected"])
        self.assertNotIn(b"private-player-id", self.path.read_bytes())

    def test_invalid_ids_and_status_do_not_change_state(self):
        self.store.save_agent(self.analysis_id, self.agent)
        with self.assertRaises(KeyError):
            self.store.get_analysis(self.analysis_id + 1)
        with self.assertRaises(KeyError):
            self.store.set_status(self.analysis_id, "inexistant", "pending")
        with self.assertRaises(ValueError):
            self.store.set_status(self.analysis_id, "rec-1", "invalid")
        self.assertEqual(self.store.get_analysis(self.analysis_id)["agent"], self.agent)

    def test_parallel_updates_preserve_both_decisions(self):
        self.store.save_agent(self.analysis_id, self.agent)
        with ThreadPoolExecutor(max_workers=2) as executor:
            accepted = executor.submit(self.store.set_status, self.analysis_id, "rec-1", "accepted")
            rejected = executor.submit(self.store.set_status, self.analysis_id, "rec-2", "rejected")
            accepted.result()
            rejected.result()
        record = self.store.get_analysis(self.analysis_id)
        self.assertEqual([r["status"] for r in record["agent"]["recommendations"]], ["accepted", "rejected"])

    def test_exports_preserve_provenance_and_escape_data(self):
        pending = self.store.get_analysis(self.analysis_id)
        self.assertIn("reste à lancer", export_html(pending).decode())
        self.store.save_agent(self.analysis_id, self.agent)
        self.store.set_status(self.analysis_id, "rec-1", "accepted")
        record = self.store.get_analysis(self.analysis_id)
        html = export_html(record).decode()
        self.assertIn("données fictives", html)
        self.assertIn("Acceptée", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        exported = json.loads(export_recommendations(record, "json"))
        self.assertTrue(exported["is_demo"])
        self.assertEqual(exported["recommendations"][0]["status"], "accepted")
        csv_text = export_recommendations(record, "csv").decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(csv_text), delimiter=";"))
        self.assertEqual(rows[0]["analyse"], "'=Formule")
        self.assertEqual(rows[0]["modification_proposée"], "'@Intérieur")
        self.assertEqual(rows[0]["justification"], "'+preuve")
        self.assertEqual(rows[0]["statut"], "Acceptée")


if __name__ == "__main__":
    unittest.main()
