---
title: Sam
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
tags:
  - 0g-hackathon
  - reachy_mini
  - reachy_mini_python_app
---

# Sam

Sam is a **Reachy Mini** medication reminder companion that runs its AI brain on
the **0G decentralized compute network**. One control loop:

> **listen** (0G Whisper STT) → *optionally* **see** (0G Qwen3-VL) → **think**
> (0G GLM-5 chat) → **speak** (local TTS) → **express** with head + antennas.

The chat model returns both *what to say* and *how it feels*, so Sam nods,
tilts, perks its antennas and bobs while talking.

Runs identically in **MuJoCo simulation** and on physical hardware.

## What's wired up

| Capability | 0G model | Status |
|---|---|---|
| 🧠 Chat / reasoning | `zai-org/GLM-5-FP8` | ✅ enabled |
| 👂 Speech-to-text | `openai/whisper-large-v3` | ✅ enabled |
| 👁️ Vision | `qwen/qwen3-vl-30b-a3b-instruct` | ⚙️ code ready, **fund a sub-account to enable** |
| 🗣️ Text-to-speech | local (`say` / `espeak`) | no 0G TTS provider yet |
| 💊 Medication reminders | local JSON + 0G Storage sync | ✅ enabled |

## Medication safety

Sam is a reminder assistant, not a doctor. It records medication instructions
that the user says came from a pharmacist or doctor, then reminds the user at the
saved times. Sam does **not** prescribe, change dosage, validate medication
instructions, identify pills as medical truth, or claim that someone swallowed a
medicine.

Sam may add a short non-prescriptive caveat when 0G intelligence or local safety
rules detect a well-known concern. For example, if a user mentions ulcer history
with naproxen, Sam can save the reminder while advising them to cross-check with
a doctor or pharmacist.

## Setup

Requires Python 3.10–3.13 (the mujoco deps don't support 3.14). We use [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[mujoco]"
cp .env.example .env   # then fill in your 0G keys (see below)
```

### 0G keys

Each provider needs its **own** host + key (a key is bound to one provider):

```bash
0g-compute-cli inference list-providers          # find provider addresses + models
0g-compute-cli inference get-secret --provider <ADDR> --duration 0
```

Copy the printed `app-sk-…` token and the `curl` host into the matching
`OG_CHAT_* / OG_STT_* / OG_VISION_*` block in `.env`.
**Mainnet = real funds** — each call spends a tiny amount of 0G.

### Hugging Face Space

This repo is a **Gradio Space** so 0G calls run server-side and API keys stay
private. In the Space settings, add these as **Secrets**:

```text
OG_CHAT_BASE_URL
OG_CHAT_MODEL
OG_CHAT_PROVIDER
OG_CHAT_API_KEY
OG_STT_BASE_URL
OG_STT_MODEL
OG_STT_PROVIDER
OG_STT_API_KEY
```

Add `OG_VISION_*` too once the vision provider is funded. Rebuild the Space after
changing secrets.

### Sam medication memory

Sam reads and writes medication memory locally first so reminders are fast and
reliable. When 0G Storage is configured, every local change is marked for sync
and a background sync keeps retrying until 0G Storage has the latest memory.

```text
SAM_MEMORY_PATH=/path/to/sam_memory.json
OG_STORAGE_ENABLED=true
OG_STORAGE_INDEXER_URL=...
OG_STORAGE_RPC_URL=...
OG_STORAGE_PRIVATE_KEY=...
OG_STORAGE_MEMORY_ROOT=...
```

`OG_STORAGE_PRIVATE_KEY` must be a secret. If 0G Storage is unavailable, Sam
continues from local JSON and keeps the memory marked as pending sync.

## Run

**1. Start the sim daemon** (separate terminal). On macOS use `--no-media`
(the daemon's media server stalls headless on a camera/mic permission prompt):

```bash
source .venv/bin/activate
reachy-mini-daemon --sim --no-media          # add --headless to skip the 3D viewer
```

**2. Talk to Sam:**

```bash
# Check real 0G config without needing the robot/sim daemon:
python -m mr_reachy --health-check --no-robot

# Single real 0G exchange without needing the robot/sim daemon:
python -m mr_reachy --once "Tell me a robot joke" --no-robot --no-speak

# Single real 0G exchange with robot/sim motion:
python -m mr_reachy --once "Tell me a robot joke"

# Type at it with robot/sim motion + local speech:
python -m mr_reachy --text

# Full voice conversation (needs a mic):
python -m mr_reachy
```

Say "what do you see?" to trigger the vision path (once a vision sub-account is funded).
Say "bye" / type `quit` to exit.

Medication demo phrases:

```text
Sam, I need to take metformin three times a day for five days.
I took it.
```

If the user does not provide exact times, Sam uses safe default reminder slots:
`09:00`, `14:00`, and `20:00` for three-times-per-day schedules.

## On the robot (demo station — Reachy Mini Wireless)

At the demo station the app runs **on the robot's Pi**, started from the dashboard
for a short slot. On hardware Sam uses the robot's **onboard mic, speaker
and camera** (via the daemon media manager) and **antenna push-to-talk** instead
of the laptop mic. In the desktop simulator, the dashboard app uses the laptop
mic/speaker path automatically. Override with `MR_REACHY_BACKEND=robot` or
`MR_REACHY_BACKEND=local` if the SDK guesses wrong.

> ⚠️ The on-robot I/O path is built against the SDK API but has **not been tested
> on a physical robot yet**. Rehearse before the slot and tune the two values below.

**1. 0G keys on the robot** — your `.env` is gitignored and does **not** travel with
the published app, and the framework injects no secrets. So the app would run but
never reach 0G. SSH into the robot and drop your keys where `config.py` looks for them:

```bash
# on the robot (over SSH):
mkdir -p ~/.config/mr_reachy
nano ~/.config/mr_reachy/.env        # paste the OG_CHAT_* / OG_STT_* lines from your local .env
```
(Alternatively point `MR_REACHY_ENV` at a keys file.) Keep keys off the public Space —
publish with `--private` if you ever bake config in.

**2. Speech — install Piper on the robot** (0G has no TTS provider):

```bash
pip install "mr-reachy[robot]"          # piper-tts + pillow
# download a voice once, then point the app at it:
export PIPER_MODEL=/path/to/en_US-amy-medium.onnx   # (+ matching .onnx.json)
```

**2. Internet** — the robot must reach the 0G endpoints
(`compute-network-*.integratenetwork.work`). Venue Wi-Fi may block this; test early.

**3. Antenna push-to-talk** — press an antenna to talk, release to send. Tune the
sensitivity if needed:

```bash
export MR_ANTENNA_THRESHOLD=0.5         # radians of deflection that counts as a press
```

**4. Publish & install:**

```bash
# Run the checker DEACTIVATED — an active venv's $VIRTUAL_ENV breaks its nested temp venv:
env -u VIRTUAL_ENV .venv/bin/reachy-mini-app-assistant check .
reachy-mini-app-assistant publish        # requires `hf auth login`
```

Then **Install to Robot** from your Hugging Face Space (dashboard URL
`http://reachy-mini.local:8000`) and start it from the dashboard. The robot
auto-returns to its rest pose when the app stops.

The app is registered via the `reachy_mini_apps` entry point
(`mr_reachy.main:MrReachy`) in `pyproject.toml`.

### Driving a robot from your machine (Lite, or testing Wireless over the network)

```bash
python -m mr_reachy --on-robot          # uses robot media + antenna push-to-talk
```

`ReachyMini()` auto-connects to a local daemon, falling back to `reachy-mini.local`.
For an explicit network connection use `connection_mode="network"`.

## Layout

```
mr_reachy/
  main.py        # ReachyMiniApp + conversation loop + CLI
  og_client.py   # 0G Compute: chat / STT / vision (OpenAI-compatible)
  medication.py  # medication plans, doses, parser, confirmation intent
  storage.py     # local JSON cache + background 0G Storage sync
  reminders.py   # due-dose reminder loop + confirmation/missed-dose handling
  io_backends.py # Local (laptop) vs Robot (onboard media + antenna push-to-talk)
  tts.py         # on-device speech synthesis (Piper / say / espeak)
  expressions.py # emotion -> head pose + antenna gestures
  audio.py       # laptop mic VAD capture + local TTS
  config.py      # loads .env into typed settings
```

See `plan.md` for the design and `agents.local.md` for environment notes.

## Validation

```bash
python -m unittest tests.test_medication tests.test_storage tests.test_reminders
python -m py_compile app.py mr_reachy/main.py mr_reachy/medication.py mr_reachy/storage.py mr_reachy/reminders.py
```
