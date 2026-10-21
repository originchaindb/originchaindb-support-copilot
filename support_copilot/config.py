from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


class CopilotError(Exception):
    """An actionable error safe to display without response bodies or credentials."""


def validate_origin(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CopilotError(f"{label} must be an HTTP(S) origin without a path or credentials.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise CopilotError(f"{label} requires HTTPS outside loopback.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    base_url: str
    tenant: str
    bearer: str = field(repr=False)
    db_user: str = ""
    db_key: str = field(default="", repr=False)
    ollama_url: str = "http://127.0.0.1:11434"
    embed_model: str = "nomic-embed-text:latest"
    chat_model: str = "qwen2.5:3b"
    cpu_only: bool = False
    namespace: str = "founder_support"
    state_dir: Path = Path(".support-copilot")
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")

    def __post_init__(self):
        if not self.allowed_hosts or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host)
            for host in self.allowed_hosts
        ):
            raise CopilotError(
                "COPILOT_ALLOWED_HOSTS must list exact hostnames, without ports or *."
            )
        validate_origin(self.base_url, "OC_BASE_URL")
        validate_origin(self.ollama_url, "OLLAMA_BASE_URL")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.tenant):
            raise CopilotError(
                "OC_TENANT must contain only letters, digits, underscores or hyphens."
            )
        if not self.bearer:
            raise CopilotError("Set OC_BEARER in your local .env file.")
        if bool(self.db_key) != bool(self.db_user):
            raise CopilotError("Set both OC_DB_USER and OC_DB_KEY, or leave both empty.")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", self.namespace):
            raise CopilotError("COPILOT_NAMESPACE must be 1–32 lowercase letters, digits or _.")

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(Path.cwd() / ".env", override=False)
        return cls(
            base_url=os.getenv("OC_BASE_URL", ""),
            tenant=os.getenv("OC_TENANT", ""),
            bearer=os.getenv("OC_BEARER", ""),
            db_user=os.getenv("OC_DB_USER", ""),
            db_key=os.getenv("OC_DB_KEY", ""),
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest"),
            chat_model=os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:3b"),
            cpu_only=os.getenv("OLLAMA_CPU_ONLY", "0") == "1",
            namespace=os.getenv("COPILOT_NAMESPACE", "founder_support"),
            state_dir=Path(os.getenv("COPILOT_STATE_DIR", ".support-copilot")),
            allowed_hosts=tuple(
                host.strip()
                for host in os.getenv("COPILOT_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
            ),
        )
