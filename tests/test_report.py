import unittest
from datetime import datetime

from sign.metabolic import Profile
from sign.report import build_summary
from sign.triage import TriageInput, assess


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(
            age=16,
            sex="female",
            height_cm=165.0,
            weight_kg=60.0,
            activity_level="Lightly Active",
        )
        self.inp = TriageInput(
            region="Respiratory / Chest",
            symptoms=("Cough", "Sore throat"),
            duration_hours=48,
            severity=5,
            progression="Getting worse",
            notes="Worse at night",
        )
        self.result = assess(self.inp)
        self.stamp = datetime(2026, 10, 25, 18, 30)

    def test_contains_the_key_facts(self):
        text = build_summary(
            self.inp,
            self.result,
            self.profile,
            [("2026-10-20", 60.5), ("2026-10-25", 60.0)],
            generated=self.stamp,
        )
        for expected in (
            "APPOINTMENT PREPARATION SUMMARY",
            "2026-10-25 18:30",
            "Age: 16",
            "Cough, Sore throat",
            "Started about: 2 days ago",
            "Severity (1-10): 5",
            "Getting worse",
            "My notes: Worse at night",
            "Latest weight: 60.0 kg",
            "2026-10-20: 60.5 kg",
            "Primary care",
            "QUESTIONS TO ASK MY CLINICIAN",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_works_without_profile_or_weights(self):
        text = build_summary(self.inp, self.result, generated=self.stamp)
        self.assertIn("No profile saved", text)
        self.assertIn("No weight entries logged", text)

    def test_limits_weights_to_five(self):
        weights = [(f"2026-10-{day:02d}", 60.0 + day) for day in range(1, 11)]
        text = build_summary(
            self.inp, self.result, self.profile, weights, generated=self.stamp
        )
        self.assertIn("2026-10-10", text)
        self.assertIn("2026-10-06", text)
        self.assertNotIn("2026-10-05", text)

    def test_lists_red_flags_when_present(self):
        inp = TriageInput(
            region="General / Systemic",
            symptoms=(),
            duration_hours=1,
            severity=2,
            progression="About the same",
            red_flags=("chest_pressure",),
        )
        text = build_summary(inp, assess(inp), generated=self.stamp)
        self.assertIn("Sudden chest pressure", text)
        self.assertIn("CALL 911 NOW", text)


if __name__ == "__main__":
    unittest.main()
