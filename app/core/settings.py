from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(alias="BOT_TOKEN")
    owner_ids: List[int] = Field(default_factory=list, alias="OWNER_IDS")
    manager_chat_ids: List[int] = Field(default_factory=list, alias="MANAGER_CHAT_IDS")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    upstream_mode: str = Field(default="DEMO", alias="UPSTREAM_MODE")
    asr_confidence_threshold: float = Field(default=0.75, alias="ASR_CONFIDENCE_THRESHOLD")
    asr_provider: str = Field(default="mock", alias="ASR_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_asr_model: str = Field(default="gpt-4o-mini-transcribe", alias="OPENAI_ASR_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com", alias="OPENAI_BASE_URL")
    asr_timeout_sec: int = Field(default=20, alias="ASR_TIMEOUT_SEC")
    asr_max_retries: int = Field(default=2, alias="ASR_MAX_RETRIES")
    asr_retry_backoff_base_sec: float = Field(default=0.7, alias="ASR_RETRY_BACKOFF_BASE_SEC")
    asr_convert_format: str = Field(default="wav", alias="ASR_CONVERT_FORMAT")
    mock_asr_text: str = Field(default="дай kpi за вчера", alias="MOCK_ASR_TEXT")
    mock_asr_confidence: float = Field(default=0.93, alias="MOCK_ASR_CONFIDENCE")
    access_deny_audit_enabled: bool = Field(default=True, alias="ACCESS_DENY_AUDIT_ENABLED")
    access_deny_audit_ttl_sec: int = Field(default=60, alias="ACCESS_DENY_AUDIT_TTL_SEC")
    access_deny_notify_once: bool = Field(default=False, alias="ACCESS_DENY_NOTIFY_ONCE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("owner_ids", mode="before")
    @classmethod
    def parse_owner_ids(cls, value: object) -> List[int]:
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            if not value.strip():
                return []
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        return []

    @field_validator("manager_chat_ids", mode="before")
    @classmethod
    def parse_manager_chat_ids(cls, value: object) -> List[int]:
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            if not value.strip():
                return []
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
