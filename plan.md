# Mr Reachy — All-in-one 0G AI companion (plan.md)

## Goal
A **Python on-robot** Reachy Mini app that does it all in one control loop:

1. **Listen** — capture mic audio, transcribe with **0G Whisper** (`openai/whisper-large-v3`).
2. **See (on request)** — grab a camera frame, describe it with **0G vision** (`qwen/qwen3-vl-30b-a3b-instruct`).
3. **Think** — reason + reply with personality via **0G chat** (`zai-org/GLM-5-FP8`).
4. **Speak** — local TTS (macOS `say` in sim / robot speaker on hardware); no TTS provider exists on the 0G marketplace today.
5. **Express** — head pose (6-DOF Stewart platform) + antennas convey emotion while listening/thinking/talking.

Runs identically in **MuJoCo simulation** (`reachy-mini-daemon --sim`) and on physical hardware.

## 0G Compute access (already configured, mainnet, chain 16661)
- Account total **4.96 0G**; funded sub-accounts: GLM-5 chat (1.2), Whisper STT (1.4); **1.4 0G** free to fund a vision sub-account.
- Access pattern: `0g-compute-cli inference get-secret --provider <addr>` → `app-sk-…` key, used with the **OpenAI Python SDK** (`base_url` = provider endpoint, `api_key` = secret).
- **Mainnet = real funds.** Per-call cost is fractions of a cent, but every test call spends real 0G.

## Open questions / to confirm during validation
- [ ] Exact OpenAI-compatible **endpoint URL** per provider (from `get-secret` output / `list-providers-detail`). Validate with curl before app code.
- [ ] Fund a **vision** sub-account (~0.5–1 0G) so the "see" feature works — OK to spend?
- [ ] TTS: confirm no 0G TTS provider; use local `say` (sim) with a pluggable interface. OK?

## Architecture
```
mr_reachy/
  app.py          # ReachyMiniApp subclass: the listen→see→think→speak→express loop
  og_client.py    # 0G Compute client (OpenAI-compatible): chat / stt / vision
  expressions.py  # emotion tag -> head pose + antenna gesture (within safety limits)
  audio.py        # mic capture (VAD) + local TTS playback
  config.py       # provider addresses, model names, endpoints, secrets from env
pyproject.toml
README.md
.env.example      # OG_* keys (gitignored)
agents.local.md   # robot/session config (AGENTS.md convention)
```

## Safety limits (SDK clamps, but we respect them)
head pitch/roll ±40°, head yaw ±180°, body yaw ±160°, |head−body yaw| ≤ 65°.

## Build steps
1. Validate 0G creds with curl (chat + STT) — no app code until this passes.
2. Install `reachy-mini[mujoco]` 1.7.3; start daemon in `--sim`; confirm dashboard at :8000.
3. Scaffold `ReachyMiniApp` (via `reachy-mini-app-assistant` per AGENTS.md).
4. Implement `og_client.py` (chat/STT/vision) + a `--text` debug mode that skips audio.
5. Implement `expressions.py` + wire the control loop in `app.py`.
6. Implement `audio.py` (mic VAD in, local TTS out).
7. Test end-to-end in sim; then document hardware run + HF Spaces publish.

## Risks
- Python **3.14.4** is very new — `reachy-mini[mujoco]`/audio wheels may not have 3.14 builds; may need a 3.11/3.12 venv.
- Mainnet spend is real (small).
- Mic/camera in MuJoCo sim are not real devices — text/file fallbacks needed for sim testing.
