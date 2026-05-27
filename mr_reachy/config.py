"""Configuration for Mr Reachy's 0G Compute services.

Secrets and endpoints are read from a project-root ``.env`` (gitignored).
Each 0G inference provider has its own host + API key (per-provider keys are
bound to a single provider, so chat/STT/vision each need their own).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root if present. Real env vars take precedence.
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class ServiceConfig:
    """One 0G inference service (OpenAI-compatible endpoint)."""

    base_url: str
    model: str
    api_key: str
    provider: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def _service(prefix: str) -> ServiceConfig:
    return ServiceConfig(
        base_url=os.getenv(f"OG_{prefix}_BASE_URL", "").strip(),
        model=os.getenv(f"OG_{prefix}_MODEL", "").strip(),
        api_key=os.getenv(f"OG_{prefix}_API_KEY", "").strip(),
        provider=os.getenv(f"OG_{prefix}_PROVIDER", "").strip(),
    )


@dataclass(frozen=True)
class Settings:
    chat: ServiceConfig
    stt: ServiceConfig
    vision: ServiceConfig

    @property
    def chat_ready(self) -> bool:
        return self.chat.enabled

    @property
    def stt_ready(self) -> bool:
        return self.stt.enabled

    @property
    def vision_ready(self) -> bool:
        return self.vision.enabled


def load_settings() -> Settings:
    return Settings(chat=_service("CHAT"), stt=_service("STT"), vision=_service("VISION"))
