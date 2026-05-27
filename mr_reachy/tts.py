"""Text-to-speech for Mr Reachy.

0G exposes no TTS provider, so speech is synthesized on-device. On the robot we
use Piper (offline, runs on the Pi); locally we fall back to macOS ``say`` or
espeak. Synthesis always yields a WAV *file path* so the caller can play it
through the right output — the robot speaker via ``media.play_sound`` on
hardware, or the default device in dev.

Configure Piper via env:
    PIPER_BIN    path to the piper binary (default: "piper" on PATH)
    PIPER_MODEL  path to a voice .onnx model (download once on the robot)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

def _piper_bin() -> str:
    return os.getenv("PIPER_BIN", "piper")


def _piper_model() -> str:
    # Read at call time so keys/config dropped on the robot (loaded into the
    # environment by config.py) are picked up regardless of import order.
    return os.getenv("PIPER_MODEL", "")


def piper_available() -> bool:
    model = _piper_model()
    return bool(shutil.which(_piper_bin()) and model and os.path.exists(model))


def synth_to_wav(text: str) -> str | None:
    """Synthesize ``text`` to a WAV file; return its path, or None on failure.

    Tries Piper first (the robot path), then macOS ``say``, then espeak-ng.
    """
    text = (text or "").strip()
    if not text:
        return None
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    # 1) Piper — preferred, offline, good quality (the robot path).
    if piper_available():
        try:
            subprocess.run(
                [_piper_bin(), "--model", _piper_model(), "--output_file", path],
                input=text.encode("utf-8"),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return path
        except Exception:
            pass

    # 2) macOS `say` to a WAV (dev convenience).
    if sys.platform == "darwin" and shutil.which("say"):
        try:
            subprocess.run(
                ["say", "-o", path, "--data-format=LEI16@22050", text], check=True
            )
            return path
        except Exception:
            pass

    # 3) espeak-ng to a WAV (generic Linux fallback).
    if shutil.which("espeak-ng"):
        try:
            subprocess.run(["espeak-ng", "-w", path, text], check=True)
            return path
        except Exception:
            pass

    if os.path.exists(path):
        os.remove(path)
    return None


def wav_duration(path: str) -> float:
    """Length of a WAV file in seconds (0.0 if unreadable)."""
    try:
        import soundfile as sf

        info = sf.info(path)
        return info.frames / float(info.samplerate)
    except Exception:
        return 0.0
