import tempfile
import unittest
from datetime import date
from pathlib import Path

from sign.database import Database
from sign.metabolic import Profile, ValidationError


def make_profile(**overrides):
    values = dict(
        age=30,
        sex="female",
        height_cm=165.0,
        weight_kg=60.0,
        activity_level="Lightly Active",
        goal="Maintenance",
        target_weight_kg=58.0,
    )
    values.update(overrides)
    return Profile(**values)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Database(Path(self._tmp.name) / "nested" / "sign.db")

    def test_no_profile_at_first(self):
        self.assertIsNone(self.db.get_profile())

    def test_profile_round_trip_and_update(self):
        profile = make_profile()
        self.db.save_profile(profile)
        self.assertEqual(self.db.get_profile(), profile)
        updated = make_profile(age=31, goal="Deficit", target_weight_kg=None)
        self.db.save_profile(updated)
        self.assertEqual(self.db.get_profile(), updated)

    def test_meals_and_daily_totals(self):
        today = date(2026, 10, 25)
        self.db.add_meal(today, "Oatmeal", 300, 10, 54, 6)
        self.db.add_meal(today, "Chicken salad", 450, 40, 15, 20)
        self.db.add_meal("2026-10-24", "Pizza", 800, 30, 90, 30)
        totals = self.db.daily_totals(today)
        self.assertEqual(totals["calories"], 750)
        self.assertEqual(totals["protein"], 50)
        self.assertEqual(len(self.db.meals_on(today)), 2)
        self.assertEqual(self.db.daily_totals("2026-01-01")["calories"], 0)

    def test_delete_meal(self):
        meal_id = self.db.add_meal("2026-10-25", "Snack", 100)
        self.db.delete_meal(meal_id)
        self.assertEqual(self.db.meals_on("2026-10-25"), [])

    def test_meal_validation(self):
        with self.assertRaises(ValidationError):
            self.db.add_meal("2026-10-25", "   ", 100)
        with self.assertRaises(ValidationError):
            self.db.add_meal("2026-10-25", "Feast", 99999)
        with self.assertRaises(ValidationError):
            self.db.add_meal("2026-10-25", "Odd", 100, protein=-1)

    def test_log_weight_updates_profile_to_newest_entry(self):
        self.db.save_profile(make_profile(weight_kg=60.0))
        self.db.log_weight("2026-10-20", 61.0)
        self.db.log_weight("2026-10-25", 59.5)
        self.assertEqual(self.db.get_profile().weight_kg, 59.5)
        # Back-dating an older entry must not overwrite the newest weight.
        self.db.log_weight("2026-10-01", 63.0)
        self.assertEqual(self.db.get_profile().weight_kg, 59.5)
        self.assertEqual(self.db.latest_weight(), ("2026-10-25", 59.5))
        self.assertEqual(
            [day for day, _ in self.db.weight_history()],
            ["2026-10-01", "2026-10-20", "2026-10-25"],
        )

    def test_log_weight_without_profile_and_validation(self):
        self.db.log_weight("2026-10-25", 70.0)
        self.assertEqual(self.db.latest_weight(), ("2026-10-25", 70.0))
        with self.assertRaises(ValidationError):
            self.db.log_weight("2026-10-25", 5.0)

    def test_clear_all(self):
        self.db.save_profile(make_profile())
        self.db.add_meal("2026-10-25", "Toast", 120)
        self.db.log_weight("2026-10-25", 60.0)
        self.db.clear_all()
        self.assertIsNone(self.db.get_profile())
        self.assertEqual(self.db.meals_on("2026-10-25"), [])
        self.assertEqual(self.db.weight_history(), [])

    def test_data_persists_between_instances(self):
        self.db.save_profile(make_profile())
        again = Database(self.db.path)
        self.assertIsNotNone(again.get_profile())


if __name__ == "__main__":
    unittest.main()
