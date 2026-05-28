"""Background reminder loop for Sam medication doses."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .medication import Dose, MedicationMemory, _now_iso
from .storage import HybridMedicationStore


MAX_REMINDERS = 3
REMINDER_CHECK_SECONDS = float(os.getenv("SAM_REMINDER_CHECK_SECONDS", "30"))
REMINDER_RETRY_SECONDS = float(os.getenv("SAM_REMINDER_RETRY_SECONDS", "300"))


@dataclass
class ReminderReply:
    speech: str
    emotion: str = "neutral"


def start_reminder_thread(
    *,
    store: HybridMedicationStore,
    stop_event: threading.Event,
    notify: Callable[[ReminderReply], None],
    check_seconds: float = REMINDER_CHECK_SECONDS,
    retry_seconds: float = REMINDER_RETRY_SECONDS,
) -> threading.Thread:
    thread = threading.Thread(
        target=_run_loop,
        kwargs={
            "store": store,
            "stop_event": stop_event,
            "notify": notify,
            "check_seconds": check_seconds,
            "retry_seconds": retry_seconds,
        },
        daemon=True,
    )
    thread.start()
    return thread


def confirm_due_dose(store: HybridMedicationStore, now: datetime | None = None) -> tuple[bool, str]:
    memory = store.load()
    due = memory.active_pending_doses(now)
    if not due:
        return False, "I do not have a due medication waiting for confirmation right now."

    dose = due[0]
    plan = memory.plan_for_dose(dose.id)
    dose.status = "confirmed"
    dose.confirmed_at = _now_iso(now)
    memory.updated_at = _now_iso(now)
    store.save(memory)
    name = plan.medication_name if plan is not None else "your medicine"
    return True, f"Thank you. I marked your {name} dose as taken."


def process_due_reminders(
    *,
    store: HybridMedicationStore,
    notify: Callable[[ReminderReply], None],
    now: datetime | None = None,
    retry_seconds: float = REMINDER_RETRY_SECONDS,
) -> bool:
    now = now or datetime.now().astimezone()
    memory = store.load()
    changed = False
    for dose in memory.active_pending_doses(now):
        if _should_mark_missed(dose):
            dose.status = "missed"
            dose.missed_at = _now_iso(now)
            changed = True
            plan = memory.plan_for_dose(dose.id)
            name = plan.medication_name if plan is not None else "your medicine"
            notify(ReminderReply(speech=f"I am worried. I could not confirm your {name} dose.", emotion="sad"))
            continue
        if _should_remind(dose, retry_seconds, now):
            plan = memory.plan_for_dose(dose.id)
            name = plan.medication_name if plan is not None else "your medicine"
            dose.reminder_count += 1
            dose.last_reminded_at = _now_iso(now)
            changed = True
            notify(
                    ReminderReply(
                    speech=f"It is time for your {name}. Please take it now, then tell me when you have taken it.",
                    emotion="thinking",
                )
            )
    if changed:
        memory.updated_at = _now_iso(now)
        store.save(memory)
    else:
        store.sync_pending_async()
    return changed


def medication_status_text(memory: MedicationMemory) -> str:
    if not memory.plans:
        return "No medication reminders saved yet."
    lines: list[str] = []
    for plan in memory.plans:
        pending = sum(1 for dose in plan.doses if dose.status == "pending")
        confirmed = sum(1 for dose in plan.doses if dose.status == "confirmed")
        missed = sum(1 for dose in plan.doses if dose.status == "missed")
        times = ", ".join(plan.dose_times)
        lines.append(
            f"{plan.medication_name}: {plan.frequency_per_day}x/day at {times} "
            f"for {plan.duration_days} days. Confirmed {confirmed}, pending {pending}, missed {missed}."
        )
    sync = "0G sync pending" if memory.pending_sync else "0G sync current"
    if memory.last_sync_error:
        sync = f"{sync}; last sync error: {memory.last_sync_error}"
    return "\n".join([*lines, sync])


def _run_loop(
    *,
    store: HybridMedicationStore,
    stop_event: threading.Event,
    notify: Callable[[ReminderReply], None],
    check_seconds: float,
    retry_seconds: float,
) -> None:
    while not stop_event.wait(check_seconds):
        process_due_reminders(store=store, notify=notify, retry_seconds=retry_seconds)


def _should_remind(dose: Dose, retry_seconds: float, now: datetime | None = None) -> bool:
    if dose.reminder_count == 0 or not dose.last_reminded_at:
        return True
    last = datetime.fromisoformat(dose.last_reminded_at)
    return ((now or datetime.now().astimezone()) - last).total_seconds() >= retry_seconds


def _should_mark_missed(dose: Dose) -> bool:
    return dose.reminder_count >= MAX_REMINDERS
