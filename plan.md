# Sam — AI Health Companion (plan.md)

## Goal
Sam is a **Reachy Mini AI health companion** built on the existing 0G robot stack. Sam's first real workflow is medication support: it listens to user-provided pharmacy instructions, uses 0G intelligence to extract a safe routine and advisory context, saves health memory locally for fast access, syncs that memory to 0G Storage, reminds the user when doses are due, and accepts voice confirmation.

Sam is a health companion, **not** a medical advisor. It records what the user says the pharmacy or doctor gave them; it does not prescribe, change dosage, verify ingestion, or identify medication as medical truth.

## What already works
1. **Listen** — capture mic audio and transcribe with 0G Whisper (`openai/whisper-large-v3`).
2. **Think** — reason and reply with 0G intelligence through 0G chat (`zai-org/GLM-5-FP8`).
3. **Speak** — local TTS in sim/dev and robot speaker support on hardware.
4. **Express** — head pose and antennas convey emotion while listening/thinking/talking.
5. **Run modes** — Hugging Face Gradio demo, local simulator, and Reachy Mini dashboard app.

## What to build
1. **Medication parsing** — detect medication setup requests and extract safe structured schedules from natural language.
2. **Hybrid health memory** — local JSON as the fast runtime cache plus 0G Storage sync for durable memory.
3. **Reminder engine** — background loop checks due doses, speaks reminders, and plays concerned/happy movements.
4. **Confirmation flow** — user can say “I took it” to mark the active dose complete.
5. **Missed dose state** — retry up to 3 times, then record the dose as missed for later caregiver escalation.
6. **Sam rebrand** — user-facing app copy, prompts, docs, and Space UI should say Sam while package names remain stable.

## Storage design
Local JSON is the source Sam reads during normal operation because reminders must be fast and reliable. 0G Storage is the durable backup/sync layer.

Environment variables:

```text
SAM_MEMORY_PATH
OG_STORAGE_ENABLED
OG_STORAGE_INDEXER_URL
OG_STORAGE_RPC_URL
OG_STORAGE_PRIVATE_KEY
OG_STORAGE_MEMORY_ROOT
```

If 0G Storage is unavailable, Sam keeps working from local JSON and logs the sync failure.

## Demo script
1. User says: “Sam, I need to take metformin three times a day for five days.”
2. Sam replies: “I’ll remind you at 9 AM, 2 PM, and 8 PM for five days. Please follow your pharmacist’s instructions.”
3. At a due time, Sam says: “It’s time for your metformin. Please take it now, then tell me when you have taken it.”
4. User says: “I took it.”
5. Sam marks the dose complete, responds happily, and records the confirmation.

## Safety
- Sam must never invent a medication, dose, or duration.
- Sam must ask for clearer instructions when the user is vague.
- Sam must not provide side-effect, interaction, or dosage advice.
- Vision confirmation is not v1; future vision can confirm visible packaging, not ingestion.
- Caregiver email is stretch only; missed-dose status is tracked now to support it later.
