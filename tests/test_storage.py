from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mr_reachy.medication import MedicationMemory, build_plan
from mr_reachy.storage import HybridMedicationStore, LocalMedicationStore


class FailingOGStore:
    def __init__(self) -> None:
        self.saved = False

    def load(self):
        return None

    def save(self, memory):
        self.saved = True
        return None


class RestoringOGStore:
    def __init__(self, memory: MedicationMemory) -> None:
        self.memory = memory

    def load(self):
        return self.memory

    def save(self, memory):
        return "0xroot"


class StorageTest(unittest.TestCase):
    def test_local_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            store = LocalMedicationStore(path)
            memory = MedicationMemory(
                plans=[
                    build_plan(
                        raw_instruction="Take metformin three times a day for five days.",
                        medication_name="metformin",
                        frequency_per_day=3,
                        duration_days=5,
                    )
                ]
            )

            store.save(memory)
            loaded = store.load()

            self.assertEqual(len(loaded.plans), 1)
            self.assertEqual(loaded.plans[0].medication_name, "metformin")

    def test_og_failure_does_not_block_local_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            og = FailingOGStore()
            store = HybridMedicationStore(LocalMedicationStore(path), og, auto_sync=False)  # type: ignore[arg-type]
            memory = MedicationMemory(
                plans=[
                    build_plan(
                        raw_instruction="Take metformin once a day for one day.",
                        medication_name="metformin",
                        frequency_per_day=1,
                        duration_days=1,
                    )
                ]
            )

            store.save(memory)
            synced = store.sync_pending()

            self.assertTrue(path.exists())
            self.assertTrue(og.saved)
            self.assertTrue(synced.pending_sync)
            self.assertEqual(len(store.load().plans), 1)

    def test_missing_local_memory_can_restore_from_og(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            memory = MedicationMemory(
                plans=[
                    build_plan(
                        raw_instruction="Take amoxicillin every morning for a week.",
                        medication_name="amoxicillin",
                        frequency_per_day=1,
                        duration_days=7,
                    )
                ]
            )
            store = HybridMedicationStore(LocalMedicationStore(path), RestoringOGStore(memory), auto_sync=False)  # type: ignore[arg-type]

            loaded = store.load()

            self.assertEqual(len(loaded.plans), 1)
            self.assertTrue(path.exists())

    def test_successful_og_sync_clears_pending_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            memory = MedicationMemory(
                plans=[
                    build_plan(
                        raw_instruction="Take metformin once a day for one day.",
                        medication_name="metformin",
                        frequency_per_day=1,
                        duration_days=1,
                    )
                ]
            )
            store = HybridMedicationStore(LocalMedicationStore(path), RestoringOGStore(memory), auto_sync=False)  # type: ignore[arg-type]

            store.save(memory)
            synced = store.sync_pending()

            self.assertFalse(synced.pending_sync)
            self.assertEqual(synced.og_storage_root, "0xroot")
            self.assertIsNotNone(synced.last_synced_at)


if __name__ == "__main__":
    unittest.main()
