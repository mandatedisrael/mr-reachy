"""Mr Reachy entry point: the conversation loop, the ReachyMiniApp, and a CLI.

The same core loop runs three ways:
  * as a published ``ReachyMiniApp`` (the daemon calls ``MrReachy.run``),
  * standalone over the daemon (``mr-reachy`` / ``python -m mr_reachy``),
  * fully offline for testing (``--mock --text --no-speak``).

Pipeline per turn:  listen -> (optionally see) -> think (0G) -> speak + express.
"""

from __future__ import annotations

import argparse
import re
import threading

from reachy_mini import ReachyMini, ReachyMiniApp

from . import audio, expressions
from .config import load_settings
from .og_client import EMOTIONS, OGClient, Reply

# Phrases that make Mr Reachy try to look and describe the scene (0G vision).
_VISION_INTENT = re.compile(
    r"\b(what (do|can) you see|look (at|around)|describe (the|what)|in front of you|see anything)\b",
    re.IGNORECASE,
)
_MAX_HISTORY_TURNS = 12  # keep the prompt small/cheap


# --------------------------------------------------------------------------- #
# Mock client for offline testing (no 0G calls, no spend).
# --------------------------------------------------------------------------- #
class MockOGClient:
    chat_enabled = True
    stt_enabled = True
    vision_enabled = False

    def chat(self, history, **_):
        last = next((t["content"] for t in reversed(history) if t["role"] == "user"), "")
        emotion = "happy"
        for e in EMOTIONS:
            if e.replace("_", " ") in last.lower():
                emotion = e
                break
        return Reply(speech=f"(mock) You said: {last}", emotion=emotion)

    def transcribe(self, wav_path):  # pragma: no cover - not used offline
        return "(mock transcription)"

    def describe(self, image_bytes, prompt="?"):  # pragma: no cover
        return "(mock) I see a cozy room."


# --------------------------------------------------------------------------- #
# Core behaviours
# --------------------------------------------------------------------------- #
def express_and_speak(reachy, reply: Reply, *, voice: str | None, speak: bool) -> None:
    """Play the emotion gesture, then speak with a synchronized talking wobble."""
    expressions.play(reachy, reply.emotion)
    if not speak or not reply.speech:
        expressions.go_rest(reachy)
        return
    _proc, done = audio.speak_async(reply.speech, voice=voice)
    # Animate the head/antennas until speech playback finishes.
    expressions.talk_animation(reachy, done)


def capture_frame(reachy) -> bytes | None:
    """Best-effort single camera frame as JPEG bytes (None if no camera)."""
    try:
        import io

        import numpy as np
        from PIL import Image  # optional; only needed for vision

        media = getattr(reachy, "media", None)
        frame = getattr(media, "last_frame", None) if media is not None else None
        if frame is None:
            return None
        img = Image.fromarray(np.asarray(frame))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None
