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


def handle_turn(reachy, og, history: list[dict], user_text: str, *, voice, speak) -> Reply:
    """Run one full think+react turn for the given user utterance."""
    user_text = user_text.strip()
    history.append({"role": "user", "content": user_text})

    # Optional vision: only if the user asked AND a vision provider is funded.
    if _VISION_INTENT.search(user_text) and getattr(og, "vision_enabled", False):
        frame = capture_frame(reachy)
        if frame is not None:
            try:
                seen = og.describe(frame, prompt="Briefly describe what you see for a friendly robot.")
                history.append({"role": "system", "content": f"[Camera] {seen}"})
            except Exception as exc:  # vision misconfigured / provider error
                history.append({"role": "system", "content": f"[Camera unavailable: {exc}]"})

    reply = og.chat(history)
    history.append({"role": "assistant", "content": reply.speech})
    # Trim history to keep prompts small/cheap.
    if len(history) > _MAX_HISTORY_TURNS * 2:
        del history[: len(history) - _MAX_HISTORY_TURNS * 2]

    print(f"  Mr Reachy [{reply.emotion}]: {reply.speech}")
    express_and_speak(reachy, reply, voice=voice, speak=speak)
    return reply


def run_conversation(
    reachy,
    stop_event: threading.Event,
    *,
    og,
    mode: str = "voice",
    voice: str | None = None,
    speak: bool = True,
) -> None:
    """The main loop. mode='voice' uses the mic; mode='text' reads stdin."""
    reachy.wake_up()
    expressions.go_rest(reachy)
    history: list[dict] = []

    greeting = Reply(speech="Hi, I'm Mr Reachy, running on the 0G network. What's up?", emotion="happy")
    print(f"  Mr Reachy [{greeting.emotion}]: {greeting.speech}")
    express_and_speak(reachy, greeting, voice=voice, speak=speak)

    while not stop_event.is_set():
        if mode == "text":
            try:
                user_text = input("\nYou> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user_text.lower() in {"quit", "exit", "bye"}:
                break
            if not user_text:
                continue
        else:  # voice
            expressions.listening_pose(reachy)
            print("\n(listening… speak now)")
            wav = audio.record_until_silence()
            if wav is None:
                continue
            user_text = og.transcribe(wav)
            print(f"You (heard)> {user_text}")
            if not user_text:
                continue
            if user_text.lower().strip(".!? ") in {"quit", "exit", "bye", "goodbye"}:
                break

        try:
            handle_turn(reachy, og, history, user_text, voice=voice, speak=speak)
        except Exception as exc:
            print(f"  [error] {exc}")
            express_and_speak(
                reachy,
                Reply(speech="Hmm, my brain hiccuped. Try again?", emotion="confused"),
                voice=voice,
                speak=speak,
            )

    expressions.go_rest(reachy)
    print("\nMr Reachy: bye!")


# --------------------------------------------------------------------------- #
# Published Reachy Mini app
# --------------------------------------------------------------------------- #
class MrReachy(ReachyMiniApp):
    """All-in-one 0G companion, runnable from the Reachy Mini dashboard."""

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        og = OGClient(load_settings())
        run_conversation(reachy_mini, stop_event, og=og, mode="voice", speak=True)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_client(mock: bool):
    if mock:
        return MockOGClient()
    settings = load_settings()
    og = OGClient(settings)
    if not og.chat_enabled:
        raise SystemExit("Chat not configured. Set OG_CHAT_* in .env (or use --mock).")
    return og


def cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mr-reachy", description="Mr Reachy — 0G companion for Reachy Mini")
    parser.add_argument("--text", action="store_true", help="type messages instead of using the mic")
    parser.add_argument("--once", metavar="MSG", help="run a single exchange with MSG, then exit")
    parser.add_argument("--mock", action="store_true", help="offline: no 0G calls (canned replies)")
    parser.add_argument("--no-speak", action="store_true", help="don't play TTS audio")
    parser.add_argument("--voice", help="TTS voice name (e.g. macOS 'Samantha')")
    args = parser.parse_args(argv)

    og = _build_client(args.mock)
    speak = not args.no_speak
    stop_event = threading.Event()

    with ReachyMini() as reachy:
        if args.once is not None:
            reachy.wake_up()
            expressions.go_rest(reachy)
            handle_turn(reachy, og, [], args.once, voice=args.voice, speak=speak)
            expressions.go_rest(reachy)
            return
        mode = "text" if (args.text or args.mock) else "voice"
        run_conversation(reachy, stop_event, og=og, mode=mode, voice=args.voice, speak=speak)


if __name__ == "__main__":
    cli()
