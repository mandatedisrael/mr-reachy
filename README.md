---
title: Mr Reachy
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: static
pinned: false
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Mr Reachy 🤖

An all-in-one **Reachy Mini** companion that runs its AI brain on the
**0G decentralized compute network**. One control loop:

> **listen** (0G Whisper STT) → *optionally* **see** (0G Qwen3-VL) → **think**
> (0G GLM-5 chat) → **speak** (local TTS) → **express** with head + antennas.

The chat model returns both *what to say* and *how it feels*, so Mr Reachy
nods, tilts, perks its antennas and bobs while talking.

Runs identically in **MuJoCo simulation** and on physical hardware.

## What's wired up

| Capability | 0G model | Status |
|---|---|---|
| 🧠 Chat / reasoning | `zai-org/GLM-5-FP8` | ✅ enabled |
| 👂 Speech-to-text | `openai/whisper-large-v3` | ✅ enabled |
| 👁️ Vision | `qwen/qwen3-vl-30b-a3b-instruct` | ⚙️ code ready, **fund a sub-account to enable** |
| 🗣️ Text-to-speech | local (`say` / `espeak`) | no 0G TTS provider yet |

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

## Run

**1. Start the sim daemon** (separate terminal). On macOS use `--no-media`
(the daemon's media server stalls headless on a camera/mic permission prompt):

```bash
source .venv/bin/activate
reachy-mini-daemon --sim --no-media          # add --headless to skip the 3D viewer
```

**2. Talk to Mr Reachy:**

```bash
# Offline smoke test — no 0G calls, no audio, just motion + parsing:
python -m mr_reachy --mock --text --no-speak

# Single live exchange (spends a little 0G):
python -m mr_reachy --once "Tell me a robot joke"

# Type at it (robot still moves + speaks):
python -m mr_reachy --text

# Full voice conversation (needs a mic):
python -m mr_reachy
```

Say "what do you see?" to trigger the vision path (once a vision sub-account is funded).
Say "bye" / type `quit` to exit.

## On real hardware

Connect to the robot's daemon instead of the sim and run the same loop, or
publish to the Reachy Mini app store:

```bash
# Run the checker DEACTIVATED — an active venv's $VIRTUAL_ENV breaks its nested temp venv:
env -u VIRTUAL_ENV .venv/bin/reachy-mini-app-assistant check .
reachy-mini-app-assistant publish        # requires `hf auth login`
```

The app is registered via the `reachy_mini_apps` entry point
(`mr_reachy.main:MrReachy`) in `pyproject.toml`.

## Layout

```
mr_reachy/
  main.py        # ReachyMiniApp + conversation loop + CLI
  og_client.py   # 0G Compute: chat / STT / vision (OpenAI-compatible)
  expressions.py # emotion -> head pose + antenna gestures
  audio.py       # mic VAD capture + local TTS
  config.py      # loads .env into typed settings
```

See `plan.md` for the design and `agents.local.md` for environment notes.
