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
