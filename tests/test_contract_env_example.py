from __future__ import annotations

from pathlib import Path


REQUIRED_KEYS = [
    "BOT_TOKEN",
    "OWNER_IDS",
    "MANAGER_CHAT_IDS",
    "ASR_PROVIDER",
    "OPENAI_API_KEY",
    "ACCESS_DENY_AUDIT_ENABLED",
    "UPSTREAM_REDIS_KEY",
    "UPSTREAM_RUNTIME_TOGGLE_ENABLED",
    "SIS_RETRY_BACKOFF_BASE_SEC",
    "SIS_MAX_RETRIES",
    "SIS_TIMEOUT_SEC",
    "SIS_OWNERBOT_API_KEY",
    "SIS_BASE_URL",
    "ACCESS_DENY_AUDIT_TTL_SEC",
    "ACCESS_DENY_NOTIFY_ONCE",
]


def test_env_example_contains_required_keys() -> None:
    source = Path("ENV.example").read_text(encoding="utf-8")
    for key in REQUIRED_KEYS:
        assert f"{key}=" in source
