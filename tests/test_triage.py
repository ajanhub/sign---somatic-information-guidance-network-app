import unittest

from sign.triage import (
    PROGRESSIONS,
    RED_FLAGS,
    SYMPTOMS,
    Tier,
    TriageInput,
    assess,
    format_duration,
    scan_free_text,
)

WORSE, SAME, BETTER = PROGRESSIONS


def make_input(**overrides):
    values = dict(
        region="General / Systemic",
        symptoms=("Fatigue or low energy",),
        duration_hours=24,
        severity=2,
        progression=SAME,
        red_flags=(),
        notes="",
    )
    values.update(overrides)
    return TriageInput(**values)


class RedFlagTests(unittest.TestCase):
    def test_every_red_flag_triggers_emergency_even_when_mild(self):
        for flag in RED_FLAGS:
            with self.subTest(flag=flag.key):
                result = assess(
                    make_input(severity=1, red_flags=(flag.key,))
                )
                self.assertIs(result.tier, Tier.EMERGENCY)
                self.assertEqual(result.red_flags[0].key, flag.key)

    def test_chest_pressure_says_call_911(self):
        result = assess(make_input(red_flags=("chest_pressure",)))
        self.assertEqual(result.headline, "CALL 911 NOW")
        self.assertIn("911", result.steps[0])

    def test_self_harm_routes_to_988(self):
        result = assess(make_input(red_flags=("self_harm",)))
        self.assertIs(result.tier, Tier.EMERGENCY)
        self.assertIn("988", result.headline)
        self.assertTrue(any("988" in step for step in result.steps))

    def test_poisoning_routes_to_poison_control(self):
        result = assess(make_input(red_flags=("poisoning",)))
        self.assertIn("POISON CONTROL", result.headline)
        self.assertTrue(any("1-800-222-1222" in s for s in result.steps))

    def test_red_flag_beats_every_other_rule(self):
        result = assess(
            make_input(
                severity=9,
                duration_hours=200,
                progression=WORSE,
                red_flags=("shortness_of_breath",),
            )
        )
        self.assertIs(result.tier, Tier.EMERGENCY)


class FreeTextTests(unittest.TestCase):
    def test_emergency_phrases_are_caught(self):
        phrases = {
            "I want to kill myself": "self_harm",
            "my chest pain is getting worse": "chest_pressure",
            "I can't breathe": "shortness_of_breath",
            "I can’t breathe": "shortness_of_breath",
            "it won't stop bleeding": "uncontrolled_bleeding",
            "my face is drooping": "stroke_signs",
            "I think I took too many pills": "poisoning",
            "I passed out earlier": "loss_of_consciousness",
        }
        for text, key in phrases.items():
            with self.subTest(text=text):
                self.assertIn(key, scan_free_text(text))

    def test_normal_text_is_not_flagged(self):
        for text in ("", "sore throat since Monday", "tired and achy"):
            with self.subTest(text=text):
                self.assertEqual(scan_free_text(text), ())

    def test_assess_escalates_on_notes(self):
        result = assess(make_input(severity=1, notes="I want to die"))
        self.assertIs(result.tier, Tier.EMERGENCY)
        self.assertIn("notes", result.reasons[0])


class TierRuleTests(unittest.TestCase):
    def test_high_severity_is_urgent(self):
        for severity in (7, 8, 10):
            with self.subTest(severity=severity):
                result = assess(make_input(severity=severity))
                self.assertIs(result.tier, Tier.URGENT)

    def test_long_and_worsening_is_urgent(self):
        result = assess(
            make_input(severity=2, duration_hours=73, progression=WORSE)
        )
        self.assertIs(result.tier, Tier.URGENT)

    def test_exactly_72_hours_worsening_is_not_urgent(self):
        result = assess(
            make_input(severity=2, duration_hours=72, progression=WORSE)
        )
        self.assertIsNot(result.tier, Tier.URGENT)

    def test_long_but_improving_is_not_urgent(self):
        result = assess(
            make_input(severity=2, duration_hours=100, progression=BETTER)
        )
        self.assertIs(result.tier, Tier.SELF_CARE)

    def test_moderate_severity_is_primary_care(self):
        for severity in (4, 5, 6):
            with self.subTest(severity=severity):
                result = assess(make_input(severity=severity))
                self.assertIs(result.tier, Tier.PRIMARY_CARE)

    def test_mild_but_longer_than_a_week_is_primary_care(self):
        result = assess(make_input(severity=2, duration_hours=8 * 24))
        self.assertIs(result.tier, Tier.PRIMARY_CARE)

    def test_caution_symptom_is_at_least_primary_care(self):
        result = assess(
            make_input(
                region="Respiratory / Chest",
                symptoms=("Wheezing",),
                severity=1,
            )
        )
        self.assertIs(result.tier, Tier.PRIMARY_CARE)

    def test_mild_is_self_care(self):
        for severity in (1, 2, 3):
            with self.subTest(severity=severity):
                result = assess(make_input(severity=severity))
                self.assertIs(result.tier, Tier.SELF_CARE)

    def test_mild_but_worsening_stays_self_care_with_a_warning(self):
        result = assess(make_input(severity=3, progression=WORSE))
        self.assertIs(result.tier, Tier.SELF_CARE)
        self.assertTrue(any("worse" in r for r in result.reasons))

    def test_every_result_has_reasons(self):
        for severity in range(1, 11):
            result = assess(make_input(severity=severity))
            self.assertTrue(result.reasons)


class InputValidationTests(unittest.TestCase):
    def test_bad_inputs_are_rejected(self):
        bad = [
            dict(region="Elbow"),
            dict(severity=0),
            dict(severity=11),
            dict(severity=5.5),
            dict(duration_hours=-1),
            dict(progression="Unknown"),
            dict(red_flags=("not_a_flag",)),
        ]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    make_input(**overrides)

    def test_lists_are_converted_so_input_is_hashable(self):
        inp = make_input(symptoms=["Headache"], red_flags=[])
        self.assertIsInstance(hash(inp), int)


class DataTests(unittest.TestCase):
    def test_all_regions_from_spec_exist(self):
        self.assertEqual(
            set(SYMPTOMS),
            {
                "General / Systemic",
                "Head / Neurological",
                "Respiratory / Chest",
                "Gastrointestinal",
                "Musculoskeletal",
                "Skin",
            },
        )

    def test_red_flag_keys_are_unique(self):
        keys = [flag.key for flag in RED_FLAGS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_format_duration(self):
        self.assertEqual(format_duration(0.5), "less than 1 hour")
        self.assertEqual(format_duration(1), "1 hour")
        self.assertEqual(format_duration(5), "5 hours")
        self.assertEqual(format_duration(72), "3 days")
        self.assertEqual(format_duration(60), "2.5 days")


if __name__ == "__main__":
    unittest.main()
