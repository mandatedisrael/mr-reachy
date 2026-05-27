# agents.local.md — Mr Reachy robot & session config

> Read by coding agents (per Pollen's AGENTS.md convention) before working here.

## App
- **Name:** Mr Reachy — all-in-one 0G companion (voice + vision + expressive motion).
- **Path:** Python on-robot app (`ReachyMiniApp` subclass at `mr_reachy/main.py:MrReachy`).
- **Plan:** see `plan.md`.

## Environment
- Python: **3.12** via `uv` (`.venv/`). `reachy-mini[mujoco]==1.7.3`.
  - The system `python3` is Homebrew 3.14 and is too new for the mujoco deps — always use `.venv`.
- Run the sim daemon with **`--no-media`** on macOS: the GStreamer media server hangs
  headless waiting on a camera/mic TCC permission dialog that never appears.
  ```bash
  source .venv/bin/activate
  reachy-mini-daemon --sim --headless --no-media --no-preload-datasets
  ```
  Use `--no-headless` (drop `--headless`) to open the MuJoCo viewer for demos.
- Audio is handled **in-app** (laptop mic via sounddevice + macOS `say`), not via the daemon.

## 0G Compute (mainnet, chain 16661)
- Secrets live in `.env` (gitignored). Three services, each its own host + `app-sk-` key.
- Funded sub-accounts: **chat** (GLM-5) and **STT** (Whisper). **Vision is NOT funded** —
  the code path exists but `OG_VISION_*` is blank, so vision is disabled until funded:
  `0g-compute-cli transfer-fund ... && 0g-compute-cli inference get-secret --provider <vision>`.
- **Mainnet = real funds.** Every chat/STT call spends a tiny amount of real 0G.

## Safety envelope (SDK clamps; gestures stay well inside)
head pitch/roll +/-40 deg, head yaw +/-180 deg, body yaw +/-160 deg, |head-body yaw| <= 65 deg.

## Publishing gotcha
`reachy-mini-app-assistant check .` spawns a nested temp venv. If you run it with the
project `.venv` **activated**, the inherited `VIRTUAL_ENV` corrupts that nested venv and
the install step fails. Run it deactivated:
```bash
env -u VIRTUAL_ENV .venv/bin/reachy-mini-app-assistant check .
```
With that, the app passes all checks (entry point `mr-reachy = mr_reachy.main:MrReachy`).

## Quick test (offline, no spend)
```bash
source .venv/bin/activate
python -m mr_reachy --mock --once "I am so happy" --no-speak
```
