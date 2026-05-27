"""How Mr Reachy hears, speaks and sees on different platforms.

``LocalBackend``  — laptop mic (sounddevice VAD) + local TTS playback. Sim/dev.
``RobotBackend``  — the Wireless robot's onboard mic / speaker / camera via
                    ``ReachyMini.media``, with **antenna push-to-talk**. This is
                    the path used when the app runs on the robot at the demo
                    station.

Both expose the same trio:
    capture(reachy)              -> wav path | None
    speak_async(reachy, text)    -> threading.Event set when playback ends
    grab_frame(reachy)           -> jpeg bytes | None

NOTE: the RobotBackend talks to real hardware and has only been exercised
against the SDK API, not a physical robot. The antenna press threshold and
whether ``media.play_sound`` blocks are the two things to tune on-device
(see MR_ANTENNA_THRESHOLD below).
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

from . import audio, tts


class LocalBackend:
    """Laptop mic + local TTS. Used in sim and during development."""

    name = "local"

    def capture(self, reachy) -> str | None:
        return audio.record_until_silence()

    def speak_async(self, reachy, text: str, voice: str | None = None) -> threading.Event:
        _proc, done = audio.speak_async(text, voice=voice)
        return done

    def grab_frame(self, reachy) -> bytes | None:
        return None  # no camera in dev/sim


class RobotBackend:
    """Onboard mic/speaker/camera via the daemon media manager.

    Push-to-talk: press an antenna (a physical button) to start listening;
    release to send. Robust in a noisy demo hall.
    """

    name = "robot"
    # Antenna deflection (radians) from the idle baseline that counts as a press.
    PRESS_THRESHOLD = float(os.getenv("MR_ANTENNA_THRESHOLD", "0.5"))
    WAIT_TIMEOUT = 30.0   # give up waiting for a press after this long
    MAX_RECORD = 15.0     # hard cap on a single utterance
    HANGOVER = 0.25       # keep recording briefly after release

    def __init__(self) -> None:
        self._media_ready = False

    def _ensure_media(self, reachy) -> None:
        if not self._media_ready:
            try:
                reachy.acquire_media()
            except Exception:
                pass
            self._media_ready = True

    def _antenna_dev(self, reachy, base) -> float:
        import numpy as np

        cur = np.asarray(reachy.get_present_antenna_joint_positions(), dtype=float)
        return float(np.max(np.abs(cur - base)))

    def capture(self, reachy) -> str | None:
        """Wait for an antenna press, record until release, return a WAV path."""
        import numpy as np
        import soundfile as sf

        self._ensure_media(reachy)
        media = reachy.media
        base = np.asarray(reachy.get_present_antenna_joint_positions(), dtype=float)

        # 1) wait for a press
        t0 = time.time()
        while self._antenna_dev(reachy, base) <= self.PRESS_THRESHOLD:
            if time.time() - t0 > self.WAIT_TIMEOUT:
                return None
            time.sleep(0.03)

        # 2) record while held (with a short hangover after release)
        media.start_recording()
        sr = media.get_input_audio_samplerate() or 16000
        chunks: list = []
        start = time.time()
        released_at: float | None = None
        try:
            while True:
                sample = media.get_audio_sample()
                if sample is not None:
                    chunks.append(np.asarray(sample, dtype=np.float32).reshape(-1))
                now = time.time()
                held = self._antenna_dev(reachy, base) > self.PRESS_THRESHOLD
                if not held and now - start > 0.3:
                    released_at = released_at or now
                    if now - released_at > self.HANGOVER:
                        break
                else:
                    released_at = None
                if now - start > self.MAX_RECORD:
                    break
                time.sleep(0.01)
        finally:
            media.stop_recording()

        if not chunks:
            return None
        data = np.concatenate(chunks)
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(path, data, int(sr), subtype="PCM_16")
        return path

    def speak_async(self, reachy, text: str, voice: str | None = None) -> threading.Event:
        self._ensure_media(reachy)
        done = threading.Event()
        wav = tts.synth_to_wav(text)
        if wav is None:
            print(f"[TTS unavailable] {text}")
            done.set()
            return done
        duration = tts.wav_duration(wav)

        def _play() -> None:
            t0 = time.time()
            try:
                reachy.media.play_sound(wav)
            except Exception as exc:
                print(f"[play_sound error] {exc}")
            # Keep the talking animation going for ~the audio length even if
            # play_sound returns immediately (i.e. is non-blocking).
            remaining = duration - (time.time() - t0)
            if remaining > 0:
                time.sleep(remaining)
            try:
                os.remove(wav)
            except OSError:
                pass
            done.set()

        threading.Thread(target=_play, daemon=True).start()
        return done

    def grab_frame(self, reachy) -> bytes | None:
        self._ensure_media(reachy)
        try:
            import io

            import numpy as np
            from PIL import Image

            frame = reachy.media.get_frame()
            if frame is None:
                return None
            buf = io.BytesIO()
            Image.fromarray(np.asarray(frame)).convert("RGB").save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        except Exception:
            return None


def select_backend(on_robot: bool):
    return RobotBackend() if on_robot else LocalBackend()
