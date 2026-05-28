from __future__ import annotations

import os
from pathlib import Path

import gradio as gr
from openai import OpenAIError

from mr_reachy.config import load_settings
from mr_reachy.medication import is_confirmation_intent, is_medication_intent, parse_medication_instruction, plan_summary
from mr_reachy.og_client import OGClient
from mr_reachy.reminders import confirm_due_dose, medication_status_text, process_due_reminders
from mr_reachy.storage import build_medication_store


def _build_client() -> OGClient:
    return OGClient(load_settings())


def _build_store():
    return build_medication_store(load_settings().storage)


def _status() -> str:
    settings = load_settings()
    parts = []
    for name, cfg in (
        ("Chat", settings.chat),
        ("Speech-to-text", settings.stt),
        ("Vision", settings.vision),
    ):
        parts.append(f"{name}: {'configured' if cfg.enabled else 'not configured'}")
    return " | ".join(parts)


def _history_for_og(history: list) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for item in history[-12:]:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content", "")
            if role in {"user", "assistant"} and content:
                turns.append({"role": role, "content": content})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            user_msg, assistant_msg = item[0], item[1]
            if user_msg:
                turns.append({"role": "user", "content": str(user_msg)})
            if assistant_msg:
                turns.append({"role": "assistant", "content": str(assistant_msg)})
    return turns


def chat(message: str, history: list) -> str:
    client = _build_client()
    store = _build_store()

    if is_confirmation_intent(message):
        confirmed, response = confirm_due_dose(store)
        return f"{response}\n\nEmotion: {'happy' if confirmed else 'curious'}"

    if is_medication_intent(message):
        result = parse_medication_instruction(message, client)
        if result.accepted and result.plan is not None:
            memory = store.load()
            memory.plans.append(result.plan)
            store.save(memory)
            return f"{plan_summary(result.plan)}\n\nEmotion: happy"
        return f"{result.reason}\n\nEmotion: confused"

    if not client.chat_enabled:
        return (
            "0G chat is not configured yet. Add OG_CHAT_BASE_URL, OG_CHAT_MODEL, "
            "OG_CHAT_PROVIDER, and OG_CHAT_API_KEY as Hugging Face Space secrets."
        )

    turns = _history_for_og(history)
    turns.append({"role": "user", "content": message})
    try:
        reply = client.chat(turns)
    except OpenAIError as exc:
        return f"0G chat request failed: {exc}"
    except Exception as exc:
        return f"Sam hit an unexpected chat error: {exc}"
    return f"{reply.speech}\n\nEmotion: {reply.emotion}"


def add_medication(instruction: str) -> tuple[str, str]:
    client = _build_client()
    store = _build_store()
    result = parse_medication_instruction(instruction, client)
    if not result.accepted or result.plan is None:
        return result.reason, medication_status_text(store.load())
    memory = store.load()
    memory.plans.append(result.plan)
    store.save(memory)
    return plan_summary(result.plan), medication_status_text(memory)


def confirm_medication() -> tuple[str, str]:
    store = _build_store()
    confirmed, response = confirm_due_dose(store)
    emotion = "happy" if confirmed else "curious"
    return f"{response}\n\nEmotion: {emotion}", medication_status_text(store.load())


def check_due_reminders() -> tuple[str, str]:
    store = _build_store()
    replies = []
    changed = process_due_reminders(store=store, notify=replies.append)
    if replies:
        response = "\n\n".join(f"{reply.speech}\nEmotion: {reply.emotion}" for reply in replies)
    elif changed:
        response = "Medication reminders were updated."
    else:
        response = "No medication dose is due right now."
    return response, medication_status_text(store.load())


def medication_status() -> str:
    return medication_status_text(_build_store().load())


def transcribe(audio_path: str | None) -> str:
    if not audio_path:
        return "Record or upload audio first."

    client = _build_client()
    if not client.stt_enabled:
        return (
            "0G speech-to-text is not configured yet. Add the OG_STT_* secrets "
            "in the Space settings."
        )
    try:
        return client.transcribe(audio_path)
    except OpenAIError as exc:
        return f"0G speech-to-text request failed: {exc}"
    except Exception as exc:
        return f"Sam hit an unexpected speech-to-text error: {exc}"


def describe(image_path: str | None) -> str:
    if not image_path:
        return "Upload an image first."

    client = _build_client()
    if not client.vision_enabled:
        return (
            "0G vision is not configured yet. Add/fund the OG_VISION_* secrets "
            "when you want the camera path enabled."
        )

    image_bytes = Path(image_path).read_bytes()
    try:
        return client.describe(image_bytes, prompt="Briefly describe what you see for a friendly robot.")
    except OpenAIError as exc:
        return f"0G vision request failed: {exc}"
    except Exception as exc:
        return f"Sam hit an unexpected vision error: {exc}"


with gr.Blocks(title="Sam") as demo:
    gr.Markdown(
        "# Sam\n"
        "A Reachy Mini AI health companion powered by 0G intelligence, with "
        "fast local memory synced to 0G Storage."
    )
    gr.Markdown(f"**0G status:** {_status()}")

    gr.ChatInterface(
        fn=chat,
        title="Talk to Sam",
        description="Chat calls 0G from the Space backend, so API keys stay private.",
    )

    with gr.Tab("Medication Plan"):
        medication_input = gr.Textbox(
            label="Pharmacy instruction",
            placeholder="Example: Take metformin three times a day for five days.",
            lines=2,
        )
        medication_response = gr.Textbox(label="Sam", lines=4)
        medication_status_box = gr.Textbox(label="Saved health memory", value=medication_status(), lines=8)
        gr.Button("Add to Sam's health plan").click(
            add_medication,
            inputs=medication_input,
            outputs=[medication_response, medication_status_box],
        )
        gr.Button("I took it").click(
            confirm_medication,
            outputs=[medication_response, medication_status_box],
        )
        gr.Button("Check due health actions").click(
            check_due_reminders,
            outputs=[medication_response, medication_status_box],
        )
        gr.Button("Refresh medication plan").click(
            medication_status,
            outputs=medication_status_box,
        )

    with gr.Tab("Speech-to-text"):
        audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Audio")
        transcript = gr.Textbox(label="Transcript", lines=4)
        gr.Button("Transcribe with 0G Whisper").click(transcribe, inputs=audio, outputs=transcript)

    with gr.Tab("Vision"):
        image = gr.Image(type="filepath", label="Image")
        description = gr.Textbox(label="Description", lines=4)
        gr.Button("Describe with 0G Vision").click(describe, inputs=image, outputs=description)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
    )
