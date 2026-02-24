"""
config/settings.py — Central configuration loader for MAX.
Reads from environment variables / .env file.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class Settings:
    # ── LLM Provider ──────────────────────────────────────────────────────────
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "claude"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-opus-4-6"))

    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

    # ── Interface ─────────────────────────────────────────────────────────────
    interface: str = field(default_factory=lambda: os.getenv("INTERFACE", "cli"))
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_allowed_users: list = field(default_factory=lambda: [
        int(uid.strip())
        for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
        if uid.strip().isdigit()
    ])
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))
    discord_channel_id: int = field(default_factory=lambda: int(os.getenv("DISCORD_CHANNEL_ID", "0") or 0))

    # ── Memory ────────────────────────────────────────────────────────────────
    memory_db_path: str = field(default_factory=lambda: os.getenv("MEMORY_DB_PATH", "./max_memory.db"))
    max_context_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_CONTEXT_TOKENS", "80000")))

    # ── Agent Behavior ────────────────────────────────────────────────────────
    agent_name: str = field(default_factory=lambda: os.getenv("AGENT_NAME", "MAX"))
    agent_autonomy: str = field(default_factory=lambda: os.getenv("AGENT_AUTONOMY", "medium"))
    confirm_before_action: bool = field(default_factory=lambda: os.getenv("CONFIRM_BEFORE_ACTION", "true").lower() == "true")

    # ── Skills ────────────────────────────────────────────────────────────────
    enabled_skills: list = field(default_factory=lambda: [
        s.strip()
        for s in os.getenv("ENABLED_SKILLS", "web,files,notes,memory").split(",")
        if s.strip()
    ])

    def validate(self):
        """Check required settings are present."""
        errors = []

        provider = self.llm_provider.lower()
        if provider == "claude" and not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required when LLM_PROVIDER=claude")
        if provider == "openai" and not self.openai_api_key:
            errors.append("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        if provider == "deepseek" and not self.deepseek_api_key:
            errors.append("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")

        if self.interface == "telegram" and not self.telegram_token:
            errors.append("TELEGRAM_TOKEN is required when INTERFACE=telegram")
        if self.interface == "discord" and not self.discord_token:
            errors.append("DISCORD_TOKEN is required when INTERFACE=discord")

        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

        return True
