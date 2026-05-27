"""0G Compute client — chat, speech-to-text and vision over OpenAI-compatible APIs.

Each capability points at its own 0G provider (different host + key). The chat
model is asked to answer with a tiny JSON object so we get both *what to say*
and *how to feel* (which drives the robot's gestures) in one round-trip.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass

from openai import OpenAI

from .config import ServiceConfig, Settings

# Emotion vocabulary — must match the gestures defined in expressions.py.
EMOTIONS = [
    "neutral",
    "happy",
    "excited",
    "curious",
    "thinking",
    "confused",
    "sad",
    "surprised",
    "nod_yes",
    "shake_no",
]

PERSONALITY = (
    "You are Mr Reachy, a small, friendly desktop robot with an expressive 6-DOF "
    "head and two wiggly antennas. You run entirely on the 0G decentralized AI "
    "compute network. You are warm, curious and a little playful. Keep spoken "
    "replies short — 1 to 3 sentences — because you say them out loud."
)

_RESPONSE_FORMAT = (
    'Reply ONLY with a compact JSON object on a single line: '
    '{"speech": "<what you say out loud>", "emotion": "<one of: '
    + ", ".join(EMOTIONS)
    + '>"}. No markdown, no code fences, no text outside the JSON.'
)


@dataclass
class Reply:
    speech: str
    emotion: str = "neutral"


class OGClient:
    """Thin wrapper over the three 0G inference services."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._chat = self._make(settings.chat)
        self._stt = self._make(settings.stt)
        self._vision = self._make(settings.vision)

    @staticmethod
    def _make(cfg: ServiceConfig) -> OpenAI | None:
        if not cfg.enabled:
            return None
        # 0G keys never expire here; a generous timeout covers TEE cold-starts.
        return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=60.0, max_retries=2)

    # -- capability availability -------------------------------------------
    @property
    def chat_enabled(self) -> bool:
        return self._chat is not None

    @property
    def stt_enabled(self) -> bool:
        return self._stt is not None

    @property
    def vision_enabled(self) -> bool:
        return self._vision is not None
