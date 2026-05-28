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
    "dance",
    "nod_yes",
    "shake_no",
]

PERSONALITY = (
    "You are Sam, a small, friendly Reachy Mini AI health companion with an "
    "expressive 6-DOF head and two wiggly antennas. Your intelligence runs on "
    "0G Compute, and your health memory can sync to 0G Storage. You are warm, "
    "careful and a little playful. You support medication routines and simple "
    "health check-ins, but you are not a medical advisor: never prescribe, "
    "change dosage, or claim a medication was swallowed. Keep spoken replies "
    "short — 1 to 3 sentences — because you say them out loud."
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

    # -- chat ---------------------------------------------------------------
    def chat(self, history: list[dict], *, temperature: float = 0.8) -> Reply:
        """history: list of {"role","content"} turns (without the system prompt)."""
        if self._chat is None:
            raise RuntimeError("Chat service is not configured (check OG_CHAT_* in .env).")
        messages = [{"role": "system", "content": f"{PERSONALITY} {_RESPONSE_FORMAT}"}, *history]
        resp = self._chat.chat.completions.create(
            model=self.settings.chat.model,
            messages=messages,
            max_tokens=300,
            temperature=temperature,
        )
        return self._parse(resp.choices[0].message.content or "")

    def complete_json(self, system_prompt: str, user_text: str, *, temperature: float = 0.0) -> str:
        """Return raw model text for strict JSON extraction tasks."""
        if self._chat is None:
            raise RuntimeError("Chat service is not configured (check OG_CHAT_* in .env).")
        resp = self._chat.chat.completions.create(
            model=self.settings.chat.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            max_tokens=400,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    @staticmethod
    def _parse(text: str) -> Reply:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                speech = str(data.get("speech", "")).strip()
                emotion = str(data.get("emotion", "neutral")).strip().lower()
                if emotion not in EMOTIONS:
                    emotion = "neutral"
                if speech:
                    return Reply(speech=speech, emotion=emotion)
            except (json.JSONDecodeError, TypeError):
                pass
        # Fall back to the raw text if the model didn't emit clean JSON.
        return Reply(speech=text.strip(), emotion="neutral")

    # -- speech to text -----------------------------------------------------
    def transcribe(self, wav_path: str) -> str:
        if self._stt is None:
            raise RuntimeError("STT service is not configured (check OG_STT_* in .env).")
        with open(wav_path, "rb") as fh:
            resp = self._stt.audio.transcriptions.create(
                model=self.settings.stt.model, file=fh
            )
        return (getattr(resp, "text", "") or "").strip()

    # -- vision -------------------------------------------------------------
    def describe(self, image_bytes: bytes, prompt: str = "Briefly describe what you see.") -> str:
        if self._vision is None:
            raise RuntimeError(
                "Vision service is not configured — fund a vision sub-account and set "
                "OG_VISION_* in .env to enable it."
            )
        b64 = base64.b64encode(image_bytes).decode("ascii")
        resp = self._vision.chat.completions.create(
            model=self.settings.vision.model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
        )
        return (resp.choices[0].message.content or "").strip()
