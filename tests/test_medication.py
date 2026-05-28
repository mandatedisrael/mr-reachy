from __future__ import annotations

import unittest
from datetime import datetime

from mr_reachy.medication import (
    build_plan,
    is_confirmation_intent,
    parse_medication_instruction,
)


class FakeOG:
    chat_enabled = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, system_prompt: str, user_text: str, *, temperature: float = 0.0) -> str:
        self.calls.append(system_prompt)
        if "Extract a medication reminder schedule" in system_prompt:
            return (
                '{"accepted": true, "medication_name": "prednisone", '
                '"frequency_per_day": 1, "duration_days": 5, "dose_times": [], '
                '"advisory_note": "", "advisory_level": "routine", "reason": "ok"}'
            )
        return (
            '{"advisory_level": "caution", '
            '"advisory_note": "Small reminder: follow the label exactly and ask your pharmacist whether to take prednisone with food."}'
        )


class MedicationParsingTest(unittest.TestCase):
    def test_three_times_per_day_defaults_to_three_daytime_slots(self) -> None:
        result = parse_medication_instruction(
            "Take metformin three times a day for five days.",
            now=datetime(2026, 5, 28, 8, 0).astimezone(),
        )

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.plan)
        assert result.plan is not None
        self.assertEqual(result.plan.medication_name.lower(), "metformin")
        self.assertEqual(result.plan.frequency_per_day, 3)
        self.assertEqual(result.plan.duration_days, 5)
        self.assertEqual(result.plan.dose_times, ["09:00", "14:00", "20:00"])
        self.assertEqual(len(result.plan.doses), 15)

    def test_one_pill_every_morning_for_week(self) -> None:
        result = parse_medication_instruction(
            "Take amoxicillin every morning for a week.",
            now=datetime(2026, 5, 28, 8, 0).astimezone(),
        )

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.plan)
        assert result.plan is not None
        self.assertEqual(result.plan.frequency_per_day, 1)
        self.assertEqual(result.plan.duration_days, 7)
        self.assertEqual(len(result.plan.doses), 7)

    def test_vague_instruction_is_rejected(self) -> None:
        result = parse_medication_instruction("Take this whenever I feel bad.")

        self.assertFalse(result.accepted)
        self.assertIsNone(result.plan)

    def test_naproxen_with_ulcer_gets_cross_check_advisory(self) -> None:
        result = parse_medication_instruction(
            "I have ulcer and they gave me naproxen twice a day for five days.",
            now=datetime(2026, 5, 28, 8, 0).astimezone(),
        )

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.plan)
        assert result.plan is not None
        self.assertEqual(result.plan.medication_name.lower(), "naproxen")
        self.assertEqual(result.plan.advisory_level, "cross_check")
        self.assertIn("cross-check", result.plan.advisory_note)

    def test_naproxen_gets_general_stomach_caution(self) -> None:
        result = parse_medication_instruction(
            "Take naproxen twice a day for five days.",
            now=datetime(2026, 5, 28, 8, 0).astimezone(),
        )

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.plan)
        assert result.plan is not None
        self.assertEqual(result.plan.advisory_level, "caution")
        self.assertIn("stomach", result.plan.advisory_note)

    def test_og_advisory_is_not_limited_to_nsaids(self) -> None:
        og = FakeOG()

        result = parse_medication_instruction(
            "They gave me prednisone once a day for five days.",
            og=og,
            now=datetime(2026, 5, 28, 8, 0).astimezone(),
        )

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.plan)
        assert result.plan is not None
        self.assertEqual(result.plan.medication_name.lower(), "prednisone")
        self.assertEqual(result.plan.advisory_level, "caution")
        self.assertIn("prednisone", result.plan.advisory_note)
        self.assertEqual(len(og.calls), 2)

    def test_confirmation_intent(self) -> None:
        self.assertTrue(is_confirmation_intent("I took it"))
        self.assertTrue(is_confirmation_intent("yes I took my medicine"))
        self.assertFalse(is_confirmation_intent("what time is my medicine"))

    def test_build_plan_rejects_vague_name(self) -> None:
        with self.assertRaises(ValueError):
            build_plan(
                raw_instruction="Take this 3 times a day for 5 days",
                medication_name="this",
                frequency_per_day=3,
                duration_days=5,
            )


if __name__ == "__main__":
    unittest.main()
