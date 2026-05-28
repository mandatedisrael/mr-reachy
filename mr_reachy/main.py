"""Sam entry point: the conversation loop, the ReachyMiniApp, and a CLI.

The same core loop runs three ways:
  * as a published ``ReachyMiniApp`` on the robot (the daemon calls ``MrReachy.run``),
  * standalone over a daemon (``mr-reachy`` / ``python -m mr_reachy``),
  * real 0G text-only checks without connecting to a robot (``--no-robot``).

Pipeline per turn:  listen -> (optionally see) -> think (0G) -> speak + express.

Hearing/speaking/seeing are delegated to an I/O backend (see io_backends.py):
LocalBackend for sim/dev (laptop mic + TTS), RobotBackend for the Wireless robot
(onboard mic/speaker/camera + antenna push-to-talk).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
import traceback
from contextlib import nullcontext

from reachy_mini import ReachyMini, ReachyMiniApp

from . import expressions
from .config import ServiceConfig, env_file_locations, load_settings
from .io_backends import LocalBackend, RobotBackend, select_backend
from .medication import is_confirmation_intent, is_medication_intent, parse_medication_instruction, plan_summary
from .og_client import OGClient, Reply
from .reminders import confirm_due_dose, start_reminder_thread
from .storage import HybridMedicationStore, build_medication_store

# Phrases that make Sam try to look and describe the scene (0G vision).
_VISION_INTENT = re.compile(
    r"\b(what (do|can) you see|look (at|around)|describe (the|what)|in front of you|see anything)\b",
    re.IGNORECASE,
)
_MAX_HISTORY_TURNS = 12  # keep the prompt small/cheap


# --------------------------------------------------------------------------- #
# Core behaviours
# --------------------------------------------------------------------------- #
def express_and_speak(reachy, reply: Reply, *, backend, voice: str | None, speak: bool) -> None:
    """Play the emotion gesture, then speak with a synchronized talking wobble."""
    if reachy is None:
        if speak and reply.speech:
            backend.speak_async(reachy, reply.speech, voice=voice).wait()
        return
    expressions.play(reachy, reply.emotion)
    if not speak or not reply.speech:
        expressions.go_rest(reachy)
        return
    done = backend.speak_async(reachy, reply.speech, voice=voice)
    # Animate the head/antennas until speech playback finishes.
    expressions.talk_animation(reachy, done)


def _safe_express_and_speak(reachy, reply: Reply, *, backend, voice: str | None = None, speak: bool = True) -> None:
    """Best-effort robot feedback for startup failures."""
    try:
        express_and_speak(reachy, reply, backend=backend, voice=voice, speak=speak)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(f"Sam fallback: {reply.speech}", file=sys.stderr, flush=True)


def handle_turn(
    reachy,
    og,
    history: list[dict],
    user_text: str,
    *,
    backend,
    voice,
    speak,
    medication_store: HybridMedicationStore | None = None,
) -> Reply:
    """Run one full think+react turn for the given user utterance."""
    user_text = user_text.strip()

    if medication_store is not None and is_confirmation_intent(user_text):
        confirmed, message = confirm_due_dose(medication_store)
        reply = Reply(speech=message, emotion="happy" if confirmed else "curious")
        print(f"  Sam [{reply.emotion}]: {reply.speech}")
        express_and_speak(reachy, reply, backend=backend, voice=voice, speak=speak)
        return reply

    if medication_store is not None and is_medication_intent(user_text):
        result = parse_medication_instruction(user_text, og)
        if result.accepted and result.plan is not None:
            memory = medication_store.load()
            memory.plans.append(result.plan)
            medication_store.save(memory)
            reply = Reply(speech=plan_summary(result.plan), emotion="happy")
        else:
            reply = Reply(speech=result.reason, emotion="confused")
        print(f"  Sam [{reply.emotion}]: {reply.speech}")
        express_and_speak(reachy, reply, backend=backend, voice=voice, speak=speak)
        return reply

    history.append({"role": "user", "content": user_text})

    # Optional vision: only if the user asked AND a vision provider is funded.
    if _VISION_INTENT.search(user_text) and getattr(og, "vision_enabled", False):
        frame = backend.grab_frame(reachy)
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

    print(f"  Sam [{reply.emotion}]: {reply.speech}")
    express_and_speak(reachy, reply, backend=backend, voice=voice, speak=speak)
    return reply


def run_conversation(
    reachy,
    stop_event: threading.Event,
    *,
    og,
    backend,
    mode: str = "voice",
    voice: str | None = None,
    speak: bool = True,
    medication_store: HybridMedicationStore | None = None,
) -> None:
    """The main loop. mode='voice' uses the backend mic; mode='text' reads stdin."""
    if reachy is None and mode != "text":
        raise RuntimeError("--no-robot can only be used with --text or --once.")

    if reachy is not None:
        reachy.wake_up()
        expressions.go_rest(reachy)
    history: list[dict] = []

    greeting = Reply(
        speech="Hi there! I'm Sam, your health buddy! It's so nice to meet you!",
        emotion="dance",
    )
    print(f"  Sam [{greeting.emotion}]: {greeting.speech}")
    express_and_speak(reachy, greeting, backend=backend, voice=voice, speak=speak)

    reminder_thread = None
    if medication_store is not None:
        reminder_thread = start_reminder_thread(
            store=medication_store,
            stop_event=stop_event,
            notify=lambda reply: express_and_speak(reachy, reply, backend=backend, voice=voice, speak=speak),
        )

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
            print("\n(listening… press an antenna / speak now)" if backend.name == "robot"
                  else "\n(listening… speak now)")
            try:
                wav = backend.capture(reachy)
            except Exception as exc:
                print(f"  [listen error] {exc}")
                express_and_speak(
                    reachy,
                    Reply(speech="I could not hear through this audio path yet.", emotion="confused"),
                    backend=backend,
                    voice=voice,
                    speak=speak,
                )
                continue
            if wav is None:
                continue
            try:
                user_text = og.transcribe(wav)
            except Exception as exc:
                print(f"  [transcribe error] {exc}")
                express_and_speak(
                    reachy,
                    Reply(speech="I heard something, but transcription failed.", emotion="confused"),
                    backend=backend,
                    voice=voice,
                    speak=speak,
                )
                continue
            print(f"You (heard)> {user_text}")
            if not user_text:
                continue
            if user_text.lower().strip(".!? ") in {"quit", "exit", "bye", "goodbye"}:
                break

        try:
            handle_turn(
                reachy,
                og,
                history,
                user_text,
                backend=backend,
                voice=voice,
                speak=speak,
                medication_store=medication_store,
            )
        except Exception as exc:
            print(f"  [error] {exc}")
            express_and_speak(
                reachy,
                Reply(speech="Hmm, my brain hiccuped. Try again?", emotion="confused"),
                backend=backend,
                voice=voice,
                speak=speak,
            )

    if reachy is not None:
        expressions.go_rest(reachy)
    if reminder_thread is not None:
        reminder_thread.join(timeout=1.0)
    print("\nSam: bye!")


# --------------------------------------------------------------------------- #
# Published Reachy Mini app (runs ON the robot, started from the dashboard)
# --------------------------------------------------------------------------- #
class MrReachy(ReachyMiniApp):
    """All-in-one 0G companion, runnable from the Reachy Mini dashboard."""

    def __init__(self, running_on_wireless: bool = False) -> None:
        super().__init__(running_on_wireless=running_on_wireless)
        self.running_on_wireless = running_on_wireless

    def _backend(self):
        choice = os.getenv("MR_REACHY_BACKEND", "auto").strip().lower()
        if choice == "local":
            return LocalBackend()
        if choice == "robot":
            return RobotBackend()
        return RobotBackend() if self.running_on_wireless else LocalBackend()

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        backend = self._backend()
        try:
            settings = load_settings()
            print(f"Sam backend: {backend.name}", flush=True)
            print(f"Sam env search: {', '.join(env_file_locations())}", flush=True)
            print(
                "Sam 0G status: "
                f"chat={'configured' if settings.chat.enabled else 'missing'}; "
                f"stt={'configured' if settings.stt.enabled else 'missing'}; "
                f"storage={'configured' if settings.storage.og_ready else 'local-only'}",
                flush=True,
            )
            og = OGClient(settings)
            medication_store = build_medication_store(settings.storage)
            if not og.chat_enabled or not og.stt_enabled:
                missing = []
                if not og.chat_enabled:
                    missing.append("OG_CHAT_*")
                if not og.stt_enabled:
                    missing.append("OG_STT_*")
                message = (
                    "I started, but I cannot talk properly yet. Add "
                    f"{' and '.join(missing)} to the robot env file, not just Hugging Face secrets."
                )
                print(f"Sam setup warning: {message}", file=sys.stderr, flush=True)
                _safe_express_and_speak(
                    reachy_mini,
                    Reply(speech=message, emotion="confused"),
                    backend=backend,
                    speak=True,
                )
                while not stop_event.wait(1.0):
                    pass
                return
            run_conversation(
                reachy_mini,
                stop_event,
                og=og,
                backend=backend,
                mode="voice",
                speak=True,
                medication_store=medication_store,
            )
        except Exception:
            traceback.print_exc(file=sys.stderr)
            _safe_express_and_speak(
                reachy_mini,
                Reply(
                    speech="Sam crashed during startup. Please open the logs and copy the traceback after the Sam startup error.",
                    emotion="confused",
                ),
                backend=backend,
                speak=True,
            )
            while not stop_event.wait(1.0):
                time.sleep(0.1)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_client() -> OGClient:
    settings = load_settings()
    og = OGClient(settings)
    if not og.chat_enabled:
        raise SystemExit("Chat not configured. Set OG_CHAT_* in .env.")
    return og


def _build_medication_store() -> HybridMedicationStore:
    return build_medication_store(load_settings().storage)


def _service_status(name: str, cfg: ServiceConfig) -> str:
    missing = []
    if not cfg.base_url:
        missing.append("BASE_URL")
    if not cfg.model:
        missing.append("MODEL")
    if not cfg.api_key:
        missing.append("API_KEY")
    if missing:
        return f"{name}: missing {', '.join(missing)}"
    return f"{name}: configured ({cfg.model})"


def run_health_check(*, check_robot: bool, host: str | None, port: int) -> int:
    """Validate real configuration and make a small live chat call."""
    settings = load_settings()
    og = OGClient(settings)

    print("Sam health check")
    print(f"  {_service_status('Chat', settings.chat)}")
    print(f"  {_service_status('Speech-to-text', settings.stt)}")
    print(f"  {_service_status('Vision', settings.vision)}")

    ok = True
    if not og.chat_enabled:
        ok = False
        print("  0G chat probe: skipped because chat is not configured")
    else:
        try:
            reply = og.chat(
                [{"role": "user", "content": "Reply with a short health check greeting."}],
                temperature=0.0,
            )
            print(f"  0G chat probe: ok [{reply.emotion}] {reply.speech}")
        except Exception as exc:
            ok = False
            print(f"  0G chat probe: failed ({exc})")

    if not og.stt_enabled:
        ok = False
        print("  0G STT: not configured")
    else:
        print("  0G STT: configured")

    if og.vision_enabled:
        print("  0G vision: configured")
    else:
        print("  0G vision: not configured; vision prompts will be skipped")

    if check_robot:
        conn = {"host": host, "port": port, "connection_mode": "network"} if host else {}
        try:
            with ReachyMini(**conn) as reachy:
                reachy.wake_up()
                expressions.go_rest(reachy)
            print("  Reachy connection: ok")
        except Exception as exc:
            ok = False
            print(f"  Reachy connection: failed ({exc})")
    else:
        print("  Reachy connection: skipped")

    return 0 if ok else 1


def cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mr-reachy", description="Sam — AI health companion for Reachy Mini")
    parser.add_argument("--text", action="store_true", help="type messages instead of listening")
    parser.add_argument("--once", metavar="MSG", help="run a single exchange with MSG, then exit")
    parser.add_argument("--health-check", action="store_true",
                        help="check real 0G configuration and make a small live chat probe")
    parser.add_argument("--no-robot", action="store_true",
                        help="skip the Reachy daemon/robot connection; only valid with --text, --once, or --health-check")
    parser.add_argument("--no-speak", action="store_true", help="don't play TTS audio")
    parser.add_argument("--on-robot", action="store_true",
                        help="use the robot's onboard mic/speaker/camera + antenna push-to-talk")
    parser.add_argument("--host", help="connect to a robot daemon at this hostname/IP "
                        "(e.g. reachy-mini.local or 192.168.1.42); omit to auto-detect a local daemon")
    parser.add_argument("--port", type=int, default=8000, help="daemon port (default: 8000)")
    parser.add_argument("--voice", help="local TTS voice name (e.g. macOS 'Samantha')")
    args = parser.parse_args(argv)

    if args.health_check:
        raise SystemExit(run_health_check(check_robot=not args.no_robot, host=args.host, port=args.port))

    if args.no_robot and not (args.text or args.once):
        raise SystemExit("--no-robot requires --text, --once, or --health-check.")

    og = _build_client()
    backend = LocalBackend() if args.no_robot else select_backend(args.on_robot)
    speak = not args.no_speak
    stop_event = threading.Event()

    # Explicit host => connect over the network to that robot; else auto-detect.
    conn = {"host": args.host, "port": args.port, "connection_mode": "network"} if args.host else {}
    reachy_context = nullcontext(None) if args.no_robot else ReachyMini(**conn)
    with reachy_context as reachy:
        if args.once is not None:
            if reachy is not None:
                reachy.wake_up()
                expressions.go_rest(reachy)
            handle_turn(
                reachy,
                og,
                [],
                args.once,
                backend=backend,
                voice=args.voice,
                speak=speak,
                medication_store=_build_medication_store(),
            )
            if reachy is not None:
                expressions.go_rest(reachy)
            return
        mode = "text" if args.text else "voice"
        run_conversation(
            reachy,
            stop_event,
            og=og,
            backend=backend,
            mode=mode,
            voice=args.voice,
            speak=speak,
            medication_store=_build_medication_store(),
        )


if __name__ == "__main__":
    cli()
