"""Configuration for Sam's 0G services and local memory.

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

# Find the 0G keys wherever the app runs. On the robot the dashboard launches the
# installed package, so the project .env isn't present — drop a keys file at
# ~/.config/mr_reachy/.env (or point MR_REACHY_ENV at one) over SSH instead.
# Real environment variables always win (load_dotenv never clobbers them); then
# the first matching file fills the gaps.
_ENV_CANDIDATES = [
    os.getenv("MR_REACHY_ENV"),
    PROJECT_ROOT / ".env",
    Path.home() / ".config" / "mr_reachy" / ".env",
    Path.home() / ".mr_reachy.env",
]
for _candidate in _ENV_CANDIDATES:
    if _candidate and Path(_candidate).is_file():
        load_dotenv(_candidate)


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


@dataclass(frozen=True)
class StorageConfig:
    """Sam medication memory storage settings."""

    memory_path: str
    enabled: bool
    indexer_url: str
    rpc_url: str
    private_key: str
    memory_root: str = ""

    @property
    def og_ready(self) -> bool:
        return bool(self.enabled and self.indexer_url and self.rpc_url and self.private_key)


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
    storage: StorageConfig

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
    default_memory_path = Path.home() / ".config" / "mr_reachy" / "sam_memory.json"
    storage = StorageConfig(
        memory_path=os.getenv("SAM_MEMORY_PATH", str(default_memory_path)).strip(),
        enabled=os.getenv("OG_STORAGE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"},
        indexer_url=os.getenv("OG_STORAGE_INDEXER_URL", "").strip(),
        rpc_url=os.getenv("OG_STORAGE_RPC_URL", "").strip(),
        private_key=os.getenv("OG_STORAGE_PRIVATE_KEY", "").strip(),
        memory_root=os.getenv("OG_STORAGE_MEMORY_ROOT", "").strip(),
    )
    return Settings(chat=_service("CHAT"), stt=_service("STT"), vision=_service("VISION"), storage=storage)
