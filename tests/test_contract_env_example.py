from __future__ import annotations

from pathlib import Path


REQUIRED_KEYS = [
    "BOT_TOKEN",
    "OWNER_IDS",
    "MANAGER_CHAT_IDS",
    "ASR_PROVIDER",
    "OPENAI_API_KEY",
    "ACCESS_DENY_AUDIT_ENABLED",
    "ACCESS_DENY_AUDIT_TTL_SEC",
    "ACCESS_DENY_NOTIFY_ONCE",
]


def test_env_example_contains_required_keys() -> None:
    source = Path("ENV.example").read_text(encoding="utf-8")
    for key in REQUIRED_KEYS:
        assert f"{key}=" in source
