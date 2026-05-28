"""Medication reminder domain for Sam.

Sam records user-provided pharmacy instructions and turns them into reminder
schedules. It does not validate, prescribe, or modify medication instructions.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any


DEFAULT_DOSE_TIMES = {
    1: ["09:00"],
    2: ["00:00", "12:00"],
    3: ["00:00", "08:00", "16:00"],
    4: ["00:00", "06:00", "12:00", "18:00"],
}

START_TIME_REQUIRED = "__START_TIME_REQUIRED__"

MEDICATION_INTENT = re.compile(
    r"\b(take|medicine|medication|drug|pill|tablet|capsule|pharmacy|pharmacist|dose|dosage)\b",
    re.IGNORECASE,
)

CONFIRMATION_INTENT = re.compile(
    r"\b(i took it|i have taken it|done|taken|i took the medicine|i took my medicine|yes i took)\b",
    re.IGNORECASE,
)

UNSAFE_MEDICAL_ADVICE = re.compile(
    r"\b(should i|can i|is it safe|side effect|interaction|overdose|double dose|skip|change|increase|reduce)\b",
    re.IGNORECASE,
)

NUMBER_WORDS = {
    "one": 1,
    "once": 1,
    "two": 2,
    "twice": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "week": 7,
}

NSAID_NAMES = {
    "aspirin",
    "ibuprofen",
    "ketoprofen",
    "naproxen",
    "diclofenac",
    "meloxicam",
    "celecoxib",
    "indomethacin",
    "piroxicam",
}

GI_RISK_WORDS = re.compile(
    r"\b(ulcer|stomach bleeding|gi bleeding|gastrointestinal bleeding|black stool|bloody stool|heartburn|gastritis)\b",
    re.IGNORECASE,
)


@dataclass
class Dose:
    id: str
    plan_id: str
    scheduled_at: str
    status: str = "pending"
    reminder_count: int = 0
    last_reminded_at: str | None = None
    confirmed_at: str | None = None
    missed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dose":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            plan_id=str(data.get("plan_id") or ""),
            scheduled_at=str(data.get("scheduled_at") or ""),
            status=str(data.get("status") or "pending"),
            reminder_count=int(data.get("reminder_count") or 0),
            last_reminded_at=data.get("last_reminded_at"),
            confirmed_at=data.get("confirmed_at"),
            missed_at=data.get("missed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "scheduled_at": self.scheduled_at,
            "status": self.status,
            "reminder_count": self.reminder_count,
            "last_reminded_at": self.last_reminded_at,
            "confirmed_at": self.confirmed_at,
            "missed_at": self.missed_at,
        }


@dataclass
class MedicationPlan:
    id: str
    medication_name: str
    raw_instruction: str
    frequency_per_day: int
    duration_days: int
    dose_times: list[str]
    start_date: str
    created_at: str
    safety_note: str
    advisory_note: str = ""
    advisory_level: str = "routine"
    doses: list[Dose] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MedicationPlan":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            medication_name=str(data.get("medication_name") or "medicine"),
            raw_instruction=str(data.get("raw_instruction") or ""),
            frequency_per_day=int(data.get("frequency_per_day") or 1),
            duration_days=int(data.get("duration_days") or 1),
            dose_times=[str(item) for item in data.get("dose_times") or DEFAULT_DOSE_TIMES[1]],
            start_date=str(data.get("start_date") or date.today().isoformat()),
            created_at=str(data.get("created_at") or _now_iso()),
            safety_note=str(data.get("safety_note") or _safety_note()),
            advisory_note=str(data.get("advisory_note") or ""),
            advisory_level=str(data.get("advisory_level") or "routine"),
            doses=[Dose.from_dict(item) for item in data.get("doses") or []],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "medication_name": self.medication_name,
            "raw_instruction": self.raw_instruction,
            "frequency_per_day": self.frequency_per_day,
            "duration_days": self.duration_days,
            "dose_times": self.dose_times,
            "start_date": self.start_date,
            "created_at": self.created_at,
            "safety_note": self.safety_note,
            "advisory_note": self.advisory_note,
            "advisory_level": self.advisory_level,
            "doses": [dose.to_dict() for dose in self.doses],
        }


@dataclass
class MedicationMemory:
    plans: list[MedicationPlan] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: _now_iso())
    og_storage_root: str | None = None
    pending_sync: bool = False
    last_synced_at: str | None = None
    last_sync_error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MedicationMemory":
        if not data:
            return cls()
        return cls(
            plans=[MedicationPlan.from_dict(item) for item in data.get("plans") or []],
            updated_at=str(data.get("updated_at") or _now_iso()),
            og_storage_root=data.get("og_storage_root"),
            pending_sync=bool(data.get("pending_sync") or False),
            last_synced_at=data.get("last_synced_at"),
            last_sync_error=data.get("last_sync_error"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plans": [plan.to_dict() for plan in self.plans],
            "updated_at": self.updated_at,
            "og_storage_root": self.og_storage_root,
            "pending_sync": self.pending_sync,
            "last_synced_at": self.last_synced_at,
            "last_sync_error": self.last_sync_error,
        }

    def active_pending_doses(self, now: datetime | None = None) -> list[Dose]:
        now = now or datetime.now().astimezone()
        doses: list[Dose] = []
        for plan in self.plans:
            for dose in plan.doses:
                if dose.status == "pending" and _parse_dt(dose.scheduled_at) <= now:
                    doses.append(dose)
        return sorted(doses, key=lambda dose: dose.scheduled_at)

    def plan_for_dose(self, dose_id: str) -> MedicationPlan | None:
        for plan in self.plans:
            if any(dose.id == dose_id for dose in plan.doses):
                return plan
        return None


@dataclass
class MedicationParseResult:
    accepted: bool
    reason: str
    plan: MedicationPlan | None = None


def is_medication_intent(text: str) -> bool:
    return bool(MEDICATION_INTENT.search(text or ""))


def is_confirmation_intent(text: str) -> bool:
    return bool(CONFIRMATION_INTENT.search(text or ""))


def parse_medication_instruction(text: str, og=None, now: datetime | None = None) -> MedicationParseResult:
    """Parse a user-provided medication reminder request into a plan."""
    text = (text or "").strip()
    if not text:
        return MedicationParseResult(False, "I need the medication instructions first.")
    if UNSAFE_MEDICAL_ADVICE.search(text):
        return MedicationParseResult(
            False,
            "I can help record reminders, but medication advice must come from your pharmacist or doctor.",
        )

    data = _parse_heuristic(text) or _parse_with_og(text, og)
    if not data:
        return MedicationParseResult(
            False,
            "I can set that up. When are you starting the first dose?",
        )
    if data.get("needs_start_time"):
        return MedicationParseResult(
            False,
            "Got it, so when are you planning to start the medication?",
        )

    advisory = _advisory_with_og(text, data, og) if og is not None else None
    if advisory:
        data["advisory_note"] = advisory.get("advisory_note") or data.get("advisory_note") or ""
        data["advisory_level"] = advisory.get("advisory_level") or data.get("advisory_level") or "routine"

    try:
        plan = build_plan(
            raw_instruction=text,
            medication_name=str(data["medication_name"]).strip(),
            frequency_per_day=int(data["frequency_per_day"]),
            duration_days=int(data["duration_days"]),
            dose_times=[str(item) for item in data.get("dose_times") or []],
            advisory_note=str(data.get("advisory_note") or ""),
            advisory_level=str(data.get("advisory_level") or "routine"),
            now=now,
        )
    except (KeyError, TypeError, ValueError):
        return MedicationParseResult(
            False,
            "I could not safely understand the medication schedule. Please say the medicine name, times per day, and number of days.",
        )
    return MedicationParseResult(True, "Medication reminder saved.", plan)


def build_plan(
    *,
    raw_instruction: str,
    medication_name: str,
    frequency_per_day: int,
    duration_days: int,
    dose_times: list[str] | None = None,
    advisory_note: str = "",
    advisory_level: str = "routine",
    now: datetime | None = None,
) -> MedicationPlan:
    now = now or datetime.now().astimezone()
    if not medication_name or medication_name.lower() in {"it", "this", "medicine", "medication", "drug"}:
        raise ValueError("Medication name is too vague.")
    if frequency_per_day < 1 or frequency_per_day > 6:
        raise ValueError("Frequency must be between 1 and 6 times per day.")
    if duration_days < 1 or duration_days > 60:
        raise ValueError("Duration must be between 1 and 60 days.")

    normalized_times = _normalize_times(dose_times or [])
    if not normalized_times:
        normalized_times = default_dose_times(frequency_per_day)
    if len(normalized_times) != frequency_per_day:
        normalized_times = default_dose_times(frequency_per_day)

    advisory_note, advisory_level = _advisory_for(
        raw_instruction=raw_instruction,
        medication_name=medication_name,
        advisory_note=advisory_note,
        advisory_level=advisory_level,
    )

    plan_id = uuid.uuid4().hex
    start = now.date()
    plan = MedicationPlan(
        id=plan_id,
        medication_name=medication_name,
        raw_instruction=raw_instruction,
        frequency_per_day=frequency_per_day,
        duration_days=duration_days,
        dose_times=normalized_times,
        start_date=start.isoformat(),
        created_at=_now_iso(now),
        safety_note=_safety_note(),
        advisory_note=advisory_note,
        advisory_level=advisory_level,
    )
    plan.doses = _make_doses(plan, start)
    return plan


def default_dose_times(frequency_per_day: int) -> list[str]:
    if frequency_per_day in DEFAULT_DOSE_TIMES:
        return list(DEFAULT_DOSE_TIMES[frequency_per_day])
    first_hour = 8
    last_hour = 20
    step = (last_hour - first_hour) / max(frequency_per_day - 1, 1)
    return [f"{round(first_hour + (step * idx)):02d}:00" for idx in range(frequency_per_day)]


def interval_dose_times(first_time: str, frequency_per_day: int) -> list[str]:
    parsed = time.fromisoformat(first_time)
    interval_hours = 24 / frequency_per_day
    values: list[str] = []
    base_minutes = parsed.hour * 60 + parsed.minute
    for idx in range(frequency_per_day):
        minutes = round(base_minutes + (idx * interval_hours * 60)) % (24 * 60)
        value = f"{minutes // 60:02d}:{minutes % 60:02d}"
        if value not in values:
            values.append(value)
    return values


def plan_summary(plan: MedicationPlan) -> str:
    joined = ", ".join(_spoken_time(item) for item in plan.dose_times)
    summary = (
        f"I'll remind you to take {plan.medication_name} {plan.frequency_per_day} "
        f"time{'s' if plan.frequency_per_day != 1 else ''} per day at {joined} "
        f"for {plan.duration_days} day{'s' if plan.duration_days != 1 else ''}. "
        "Please follow your pharmacist's or doctor's instructions."
    )
    if plan.advisory_note:
        summary = f"{summary} {plan.advisory_note}"
    return summary


def _parse_with_og(text: str, og) -> dict[str, Any] | None:
    if og is None or not getattr(og, "chat_enabled", False):
        return None
    prompt = (
        "Extract a medication reminder schedule from the user's words. Return ONLY JSON "
        "with keys: accepted, medication_name, frequency_per_day, duration_days, dose_times, "
        "advisory_note, advisory_level, reason. "
        "Use accepted=false if the request asks for medical advice, is vague, lacks a medication name, "
        "or lacks frequency/duration. dose_times must be HH:MM strings or an empty list. "
        "You may leave advisory_note empty here; a second 0G call will generate medication-specific "
        "advisory context."
    )
    try:
        raw = og.complete_json(prompt, text, temperature=0.0)
        data = _extract_json(raw)
    except Exception:
        return None
    if not data or data.get("accepted") is False:
        return None
    return data


def _advisory_with_og(text: str, data: dict[str, Any], og) -> dict[str, Any] | None:
    if og is None or not getattr(og, "chat_enabled", False):
        return None
    medication_name = str(data.get("medication_name") or "").strip()
    if not medication_name:
        return None
    prompt = (
        "You generate a short medication reminder advisory for Sam, a reminder-only robot. "
        "Use general medication knowledge from 0G intelligence and the user's stated context. "
        "Return ONLY JSON with keys: advisory_level and advisory_note. advisory_level must be "
        "routine, caution, or cross_check. advisory_note must be one short non-prescriptive caveat "
        "that helps the user use the medication as instructed, such as follow the label, ask whether "
        "to take with food, avoid known duplicate-risk categories, or cross-check with a doctor or "
        "pharmacist when the user's condition/context suggests a known concern. Do not say the drug "
        "is safe or unsafe. Do not diagnose, prescribe, change dosage, or mention rare exhaustive risks. "
        "If there is no useful caveat, return routine with an empty advisory_note."
    )
    user = (
        f"Medication: {medication_name}\n"
        f"Frequency per day: {data.get('frequency_per_day')}\n"
        f"Duration days: {data.get('duration_days')}\n"
        f"User words: {text}"
    )
    try:
        raw = og.complete_json(prompt, user, temperature=0.0)
        advisory = _extract_json(raw)
    except Exception:
        return None
    if not advisory:
        return None
    level = str(advisory.get("advisory_level") or "routine").strip().lower()
    note = str(advisory.get("advisory_note") or "").strip()
    if level not in {"routine", "caution", "cross_check"}:
        level = "routine"
    return {"advisory_level": level, "advisory_note": note}


def _parse_heuristic(text: str) -> dict[str, Any] | None:
    frequency = _find_frequency(text)
    duration = _find_duration(text)
    name = _find_medication_name(text)
    if not frequency or not duration or not name:
        return None
    found_times = _find_times(text)
    if len(found_times) == 1 and frequency > 1:
        found_times = interval_dose_times(found_times[0], frequency)
    elif not found_times:
        start_time = _find_start_time(text)
        if start_time == START_TIME_REQUIRED:
            return {
                "accepted": False,
                "needs_start_time": True,
                "medication_name": name,
                "frequency_per_day": frequency,
                "duration_days": duration,
                "dose_times": [],
                "advisory_note": "",
                "advisory_level": "routine",
                "reason": "Start time is needed.",
            }
        found_times = interval_dose_times(start_time, frequency)
    return {
        "accepted": True,
        "medication_name": name,
        "frequency_per_day": frequency,
        "duration_days": duration,
        "dose_times": found_times,
        "advisory_note": "",
        "advisory_level": "routine",
        "reason": "Parsed with local fallback.",
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _find_frequency(text: str) -> int | None:
    lower = text.lower()
    if re.search(r"\b(at night|nightly|every night|bedtime|every morning|once daily|once a day)\b", lower):
        return 1
    match = re.search(r"(\d+)\s*(times?|x)\s*(a|per)?\s*day", lower)
    if match:
        return int(match.group(1))
    for word, value in NUMBER_WORDS.items():
        if word in {"once", "twice"} and re.search(rf"\b{word}\b\s*(a|per)?\s*day", lower):
            return value
        if re.search(rf"\b{word}\b\s+times?\s*(a|per)?\s*day", lower):
            return value
    return None


def _find_duration(text: str) -> int | None:
    lower = text.lower()
    if re.search(r"\bfor\s+(a|one)\s+week\b", lower):
        return 7
    if re.search(r"\bfor\s+(a|one)\s+day\b", lower):
        return 1
    match = re.search(r"for\s+(\d+)\s*(days?|weeks?)", lower)
    if match:
        value = int(match.group(1))
        return value * 7 if match.group(2).startswith("week") else value
    for word, value in NUMBER_WORDS.items():
        match = re.search(rf"for\s+{word}\s*(days?|weeks?)", lower)
        if match:
            return value * 7 if match.group(1).startswith("week") else value
    return None


def _find_medication_name(text: str) -> str | None:
    match = re.search(
        r"\b(?:take|given me|gave me|use)\s+(?:my\s+|the\s+)?([a-zA-Z][a-zA-Z0-9_-]{2,})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    name = match.group(1).strip(" .,")
    if name.lower() in {"this", "that", "medicine", "medication", "drug", "pill", "tablet", "capsule"}:
        return None
    return name


def _find_times(text: str) -> list[str]:
    found: list[str] = []
    for hour, minute, ampm in re.findall(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE):
        hour_int = int(hour)
        if ampm.lower() == "pm" and hour_int != 12:
            hour_int += 12
        if ampm.lower() == "am" and hour_int == 12:
            hour_int = 0
        found.append(f"{hour_int:02d}:{int(minute or 0):02d}")
    return _normalize_times(found)


def _find_start_time(text: str) -> str:
    lower = text.lower()
    explicit = _find_times(text)
    if explicit:
        return explicit[0]
    if re.search(r"\b(start|starting|first dose|first one|begin|beginning)\b.*\b(now|today|immediately)\b", lower):
        return datetime.now().astimezone().strftime("%H:%M")
    if re.search(r"\b(at night|nightly|every night|bedtime)\b", lower):
        return "21:00"
    if re.search(r"\b(morning|every morning)\b", lower):
        return "09:00"
    if re.search(r"\b(afternoon)\b", lower):
        return "14:00"
    if re.search(r"\b(evening)\b", lower):
        return "18:00"
    return START_TIME_REQUIRED


def _normalize_times(items: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        try:
            parsed = time.fromisoformat(item)
        except ValueError:
            continue
        value = f"{parsed.hour:02d}:{parsed.minute:02d}"
        if value not in normalized:
            normalized.append(value)
    return normalized


def _make_doses(plan: MedicationPlan, start: date) -> list[Dose]:
    doses: list[Dose] = []
    for day_offset in range(plan.duration_days):
        current = start + timedelta(days=day_offset)
        for dose_time in plan.dose_times:
            scheduled = datetime.combine(current, time.fromisoformat(dose_time)).astimezone()
            doses.append(
                Dose(
                    id=uuid.uuid4().hex,
                    plan_id=plan.id,
                    scheduled_at=scheduled.isoformat(),
                )
            )
    return doses


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now().astimezone()).isoformat()


def _spoken_time(value: str) -> str:
    parsed = time.fromisoformat(value)
    suffix = "AM" if parsed.hour < 12 else "PM"
    hour = parsed.hour % 12 or 12
    return f"{hour}:{parsed.minute:02d} {suffix}"


def _safety_note() -> str:
    return "Reminder only. Follow pharmacist or doctor instructions."


def _advisory_for(
    *,
    raw_instruction: str,
    medication_name: str,
    advisory_note: str,
    advisory_level: str,
) -> tuple[str, str]:
    note = (advisory_note or "").strip()
    level = advisory_level if advisory_level in {"routine", "caution", "cross_check"} else "routine"
    med = medication_name.lower().strip()
    raw = raw_instruction.lower()

    if med in NSAID_NAMES and GI_RISK_WORDS.search(raw):
        return (
            f"Because you mentioned a stomach/ulcer concern with {med}, please cross-check "
            "with your doctor or pharmacist before taking it. If they already confirmed it, "
            "follow their label exactly.",
            "cross_check",
        )

    if med in NSAID_NAMES and not note:
        return (
            f"Small reminder: {med} can upset the stomach for some people; follow the label, "
            "and ask your pharmacist whether to take it with food or milk.",
            "caution",
        )

    return note, level
