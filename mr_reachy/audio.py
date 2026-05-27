"""Audio I/O for Mr Reachy: mic capture (with simple VAD) and local TTS.

Kept deliberately decoupled from the robot daemon's media server: on macOS the
daemon's GStreamer media stack stalls headless, so in simulation we use the
laptop mic + the built-in ``say`` command. On real hardware you can instead
route audio through the robot. Heavy audio imports are lazy so text-only mode
never needs a working audio device.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading

SAMPLE_RATE = 16000  # whisper-large-v3 expects 16 kHz mono


def record_until_silence(
    *,
    max_seconds: float = 12.0,
    silence_seconds: float = 1.2,
    start_timeout: float = 8.0,
    calibrate_seconds: float = 0.4,
    margin: float = 3.0,
) -> str | None:
    """Record from the default mic until the speaker goes quiet.

    Returns the path to a 16 kHz mono WAV file, or None if no speech started.
    Uses a simple energy gate calibrated from the ambient level at the start.
    """
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    block = int(SAMPLE_RATE * 0.05)  # 50 ms blocks
    frames: list["np.ndarray"] = []

    def rms(buf):
        return float(np.sqrt(np.mean(np.square(buf.astype(np.float32)))) + 1e-9)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block) as stream:
        # Calibrate ambient noise floor.
        ambient = []
        for _ in range(int(calibrate_seconds / 0.05)):
            buf, _ = stream.read(block)
            ambient.append(rms(buf[:, 0]))
        floor = sum(ambient) / max(len(ambient), 1)
        threshold = floor * margin

        started = False
        silent_for = 0.0
        elapsed = 0.0
        while True:
            buf, _ = stream.read(block)
            mono = buf[:, 0]
            level = rms(mono)
            elapsed += 0.05
            if not started:
                if level > threshold:
                    started = True
                    frames.append(mono.copy())
                elif elapsed > start_timeout:
                    return None
                continue
            frames.append(mono.copy())
            silent_for = silent_for + 0.05 if level <= threshold else 0.0
            if silent_for >= silence_seconds or elapsed >= max_seconds:
                break

    if not frames:
        return None
    audio = np.concatenate(frames)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
    return path


def _tts_command(text: str, voice: str | None) -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("say"):
        cmd = ["say"]
        if voice:
            cmd += ["-v", voice]
        return [*cmd, text]
    if shutil.which("espeak-ng"):
        return ["espeak-ng", text]
    if shutil.which("espeak"):
        return ["espeak", text]
    return None


def speak(text: str, voice: str | None = None) -> None:
    """Blocking TTS playback. Falls back to printing if no engine is available."""
    cmd = _tts_command(text, voice)
    if cmd is None:
        print(f"[TTS unavailable] {text}")
        return
    subprocess.run(cmd, check=False)
