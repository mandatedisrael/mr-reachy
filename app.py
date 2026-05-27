from __future__ import annotations

import os
from pathlib import Path

import gradio as gr
from openai import OpenAIError

from mr_reachy.config import load_settings
from mr_reachy.og_client import OGClient


def _build_client() -> OGClient:
    return OGClient(load_settings())


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
        return f"Mr Reachy hit an unexpected chat error: {exc}"
    return f"{reply.speech}\n\nEmotion: {reply.emotion}"


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
        return f"Mr Reachy hit an unexpected speech-to-text error: {exc}"


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
        return f"Mr Reachy hit an unexpected vision error: {exc}"


with gr.Blocks(title="Mr Reachy") as demo:
    gr.Markdown(
        "# Mr Reachy\n"
        "A server-side Hugging Face demo for the Reachy Mini companion powered by 0G Compute."
    )
    gr.Markdown(f"**0G status:** {_status()}")

    gr.ChatInterface(
        fn=chat,
        title="Talk to Mr Reachy",
        description="Chat calls 0G from the Space backend, so API keys stay private.",
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
