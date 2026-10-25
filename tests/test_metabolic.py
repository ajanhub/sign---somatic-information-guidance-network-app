import unittest

from sign.metabolic import (
    ACTIVITY_LEVELS,
    Profile,
    ValidationError,
    bmr,
    calorie_targets,
    cm_to_feet_inches,
    feet_inches_to_cm,
    format_height,
    format_weight,
    kg_to_lbs,
    lbs_to_kg,
    macro_breakdown,
    tdee,
    weight_from_display,
    weight_to_display,
)


def make_profile(**overrides):
    values = dict(
        age=30,
        sex="male",
        height_cm=180.0,
        weight_kg=80.0,
        activity_level="Sedentary",
        goal="Maintenance",
    )
    values.update(overrides)
    return Profile(**values)


class FormulaTests(unittest.TestCase):
    def test_bmr_male_matches_mifflin_st_jeor(self):
        # 10*80 + 6.25*180 - 5*30 + 5 = 1780
        self.assertAlmostEqual(bmr(make_profile()), 1780.0)

    def test_bmr_female_matches_mifflin_st_jeor(self):
        profile = make_profile(
            age=25, sex="female", height_cm=165.0, weight_kg=60.0
        )
        # 10*60 + 6.25*165 - 5*25 - 161 = 1345.25
        self.assertAlmostEqual(bmr(profile), 1345.25)

    def test_tdee_uses_activity_multiplier(self):
        for level, factor in ACTIVITY_LEVELS.items():
            profile = make_profile(activity_level=level)
            self.assertAlmostEqual(tdee(profile), 1780.0 * factor)

    def test_activity_multipliers_match_spec(self):
        self.assertEqual(
            ACTIVITY_LEVELS,
            {
                "Sedentary": 1.2,
                "Lightly Active": 1.375,
                "Moderately Active": 1.55,
                "Very Active": 1.725,
            },
        )


class CalorieTargetTests(unittest.TestCase):
    def test_adult_gets_plus_and_minus_400(self):
        targets = calorie_targets(make_profile())
        self.assertEqual(targets.maintenance, 2136)
        self.assertEqual(targets.deficit, 1736)
        self.assertEqual(targets.surplus, 2536)
        self.assertEqual(targets.selected, 2136)
        self.assertEqual(targets.selected_goal, "Maintenance")

    def test_selected_follows_goal(self):
        deficit = calorie_targets(make_profile(goal="Deficit"))
        surplus = calorie_targets(make_profile(goal="Surplus"))
        self.assertEqual(deficit.selected, 1736)
        self.assertEqual(surplus.selected, 2536)

    def test_under_18_only_gets_maintenance(self):
        targets = calorie_targets(make_profile(age=16, goal="Deficit"))
        self.assertIsNone(targets.deficit)
        self.assertIsNone(targets.surplus)
        self.assertEqual(targets.selected, targets.maintenance)
        self.assertEqual(targets.selected_goal, "Maintenance")
        self.assertTrue(targets.notes)

    def test_deficit_never_below_1200(self):
        profile = make_profile(
            age=40,
            sex="female",
            height_cm=155.0,
            weight_kg=50.0,
            goal="Deficit",
        )
        targets = calorie_targets(profile)
        self.assertGreater(targets.maintenance, 1200)
        self.assertGreaterEqual(targets.deficit, 1200)

    def test_no_deficit_when_underweight(self):
        profile = make_profile(
            sex="female", height_cm=170.0, weight_kg=48.0, goal="Deficit"
        )
        targets = calorie_targets(profile)
        self.assertIsNone(targets.deficit)
        self.assertEqual(targets.selected_goal, "Maintenance")


class ValidationTests(unittest.TestCase):
    def test_rejects_bad_values(self):
        bad = [
            dict(age=5),
            dict(age=150),
            dict(sex="other"),
            dict(height_cm=50.0),
            dict(weight_kg=5.0),
            dict(weight_kg=500.0),
            dict(target_weight_kg=10.0),
            dict(activity_level="Couch"),
            dict(goal="Bulk"),
        ]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValidationError):
                    make_profile(**overrides)


class UnitTests(unittest.TestCase):
    def test_pound_kilogram_round_trip(self):
        self.assertAlmostEqual(lbs_to_kg(kg_to_lbs(72.5)), 72.5)
        self.assertAlmostEqual(lbs_to_kg(150), 68.0388555)

    def test_height_conversion(self):
        self.assertAlmostEqual(feet_inches_to_cm(5, 9), 175.26)
        self.assertEqual(cm_to_feet_inches(175.26), (5, 9))
        self.assertEqual(cm_to_feet_inches(182.88), (6, 0))

    def test_display_helpers(self):
        self.assertEqual(weight_to_display(68.0, "imperial"), 149.9)
        self.assertEqual(weight_to_display(68.0, "metric"), 68.0)
        self.assertAlmostEqual(weight_from_display(150.0, "imperial"), 68.04, 2)
        self.assertEqual(format_weight(68.0, "metric"), "68.0 kg")
        self.assertEqual(format_height(175.26, "imperial"), "5 ft 9 in")
        self.assertEqual(format_height(175.26, "metric"), "175 cm")


class MacroTests(unittest.TestCase):
    def test_percentages_sum_to_100(self):
        result = macro_breakdown(30, 50, 10)
        total = sum(item["percent"] for item in result.values())
        self.assertAlmostEqual(total, 100.0)
        self.assertEqual(result["protein"]["kcal"], 120)
        self.assertEqual(result["fats"]["kcal"], 90)

    def test_zero_macros(self):
        result = macro_breakdown(0, 0, 0)
        self.assertTrue(all(item["percent"] == 0.0 for item in result.values()))


if __name__ == "__main__":
    unittest.main()
