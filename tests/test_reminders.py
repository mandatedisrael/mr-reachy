from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from mr_reachy.medication import MedicationMemory, build_plan
from mr_reachy.reminders import confirm_due_dose, process_due_reminders
from mr_reachy.storage import HybridMedicationStore, LocalMedicationStore


def _store_with_due_plan(tmp: str) -> tuple[HybridMedicationStore, datetime]:
    now = datetime(2026, 5, 28, 9, 5).astimezone()
    plan = build_plan(
        raw_instruction="Take metformin once a day for one day.",
        medication_name="metformin",
        frequency_per_day=1,
        duration_days=1,
        dose_times=["09:00"],
        now=now,
    )
    store = HybridMedicationStore(LocalMedicationStore(Path(tmp) / "memory.json"), auto_sync=False)
    store.save(MedicationMemory(plans=[plan]))
    return store, now


class ReminderTest(unittest.TestCase):
    def test_due_dose_triggers_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, now = _store_with_due_plan(tmp)
            replies = []

            changed = process_due_reminders(store=store, notify=replies.append, now=now)
            memory = store.load()

            self.assertTrue(changed)
            self.assertEqual(len(replies), 1)
            self.assertIn("metformin", replies[0].speech)
            self.assertEqual(memory.plans[0].doses[0].reminder_count, 1)

    def test_confirmation_marks_due_dose_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, now = _store_with_due_plan(tmp)

            confirmed, message = confirm_due_dose(store, now=now)
            memory = store.load()

            self.assertTrue(confirmed)
            self.assertIn("metformin", message)
            self.assertEqual(memory.plans[0].doses[0].status, "confirmed")

    def test_missed_dose_after_three_reminders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, now = _store_with_due_plan(tmp)
            memory = store.load()
            dose = memory.plans[0].doses[0]
            dose.reminder_count = 3
            dose.last_reminded_at = (now - timedelta(minutes=10)).isoformat()
            store.save(memory)
            replies = []

            changed = process_due_reminders(store=store, notify=replies.append, now=now)
            updated = store.load()

            self.assertTrue(changed)
            self.assertEqual(updated.plans[0].doses[0].status, "missed")
            self.assertEqual(replies[0].emotion, "sad")


if __name__ == "__main__":
    unittest.main()
