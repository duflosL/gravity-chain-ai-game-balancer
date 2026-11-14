import json
from pathlib import Path
import unittest

from balancer.analytics import CsvError, analyze, load_csv


DEMO = Path(__file__).resolve().parents[1] / "data" / "demo.csv"


class CsvTests(unittest.TestCase):
    def test_optional_columns_and_days_are_reported(self):
        csv = ("session_id;level;success;attempts;timing_accuracy_pct;played_at;email\n"
               "001;Périgée;oui;1;91,5;2026-10-20T23:56:00-02:00;ignorée\n"
               "002;Périgée;non;3;;2026-10-21;ignorée\n"
               "001;Orbite;1;2;100;;ignorée\n").encode("utf-8-sig")
        frame, warnings = load_csv(csv)
        self.assertEqual(list(frame["session_id"]), ["001", "002", "001"])
        self.assertNotIn("email", frame)
        self.assertEqual(len(warnings), 3)
        stats = analyze(frame)
        self.assertEqual(stats["overview"]["sessions"], 2)
        self.assertEqual(stats["overview"]["success_rate"], 66.67)
        self.assertEqual(stats["overview"]["failure_rate"], 33.33)
        self.assertEqual(stats["overview"]["avg_attempts"], 2)
        self.assertEqual(stats["overview"]["avg_timing_accuracy_pct"], 95.75)
        self.assertEqual(stats["trend_coverage_n"], 2)
        self.assertEqual(stats["trend"], [{"period": "2026-10-21", "n": 2, "success_rate": 50, "avg_attempts": 2}])
        self.assertEqual(stats["findings"], [])
        self.assertIsNone(stats["levels"][0]["timing_gap_pct_points"])
        json.dumps(stats, allow_nan=False)

    def test_invalid_files_explain_the_location_or_schema(self):
        header = "session_id,level,success,attempts,timing_accuracy_pct,played_at\n"
        invalid = (
            ("session_id,success\na,1\n", "obligatoires"),
            ("session_id,level,success,attempts,level\n", "nom distinct"),
            (header, "au moins une ligne"),
            (header + "a,b,1,2\n", "ligne 2"),
            (header + "a,b,maybe,2,80,\n", "success.*2"),
            (header + "a,b,1,1.5,80,\n", "attempts.*2"),
            (header + "a,b,1,,80,\n", "attempts.*2"),
            (header + "a,b,1,2,101,\n", "timing_accuracy_pct.*2"),
            (header + "a,b,1,2,inf,\n", "timing_accuracy_pct.*2"),
            (header + "a,b,1,2,80,20/10/2026\n", "played_at.*2"),
            (header + "a,b,1,2,70,\na,b,1,2,80,\n", "session_id / level.*3"),
            (header + '"unclosed,b,1,2,70,\n', "Format CSV invalide"),
        )
        for content, message in invalid:
            with self.subTest(content=content), self.assertRaisesRegex(CsvError, message):
                load_csv(content.encode())

    def test_all_optional_fields_can_be_absent(self):
        frame, warnings = load_csv(b"session_id,level,success,attempts\n0001,Probe,1,1\n")
        stats = analyze(frame)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(stats["trend"], [])
        self.assertEqual(stats["overview"]["success_rate"], 100)
        self.assertEqual(stats["levels"][0]["success_ci_high"], 100)
        self.assertIsNone(stats["levels"][0]["avg_duration_s"])

    def test_threshold_includes_an_exact_gap_and_requires_coverage(self):
        header = 'session_id;level;success;attempts;"ignore,quoted,extra,comma,field"'
        rows = [header]
        for level, size, successes in (("A", 20, 11), ("B", 20, 14), ("C", 1, 1)):
            rows.extend(f"{i};{level};{int(i < successes)};1;_" for i in range(size))
        frame, _ = load_csv(("\n".join(rows[:-1])).encode())
        self.assertEqual(analyze(frame)["findings"][0]["metrics"]["gap_pct_points"], 15)
        frame, _ = load_csv(("\n".join(rows)).encode())
        self.assertEqual([item["level"] for item in analyze(frame)["findings"]], ["A"])

    def test_demo_produces_reproducible_bottleneck(self):
        frame, warnings = load_csv(DEMO.read_bytes())
        result = analyze(frame)
        self.assertEqual(result, analyze(frame))
        self.assertEqual(result["overview"]["sessions"], 150)
        self.assertEqual(result["overview"]["levels"], 5)
        self.assertEqual(len(result["trend"]), 10)
        self.assertEqual([item["level"] for item in result["findings"]], ["Périgée"])
        self.assertGreater(result["findings"][0]["metrics"]["gap_pct_points"], 30)
        self.assertGreater(result["findings"][0]["metrics"]["timing_gap_pct_points"], 7)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
