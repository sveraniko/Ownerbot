from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_list_env(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("JSON list env value must be an array.")
            return parsed
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    owner_ids: Annotated[List[int], NoDecode] = Field(default_factory=list, alias="OWNER_IDS")
    manager_chat_ids: Annotated[List[int], NoDecode] = Field(default_factory=list, alias="MANAGER_CHAT_IDS")
    database_url: str = Field(default="sqlite+aiosqlite:///:memory:", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    upstream_mode: str = Field(default="DEMO", alias="UPSTREAM_MODE")
    sis_base_url: str = Field(default="", alias="SIS_BASE_URL")
    sis_ownerbot_api_key: str = Field(default="", alias="SIS_OWNERBOT_API_KEY")
    sis_timeout_sec: int = Field(default=15, alias="SIS_TIMEOUT_SEC")
    sis_max_retries: int = Field(default=2, alias="SIS_MAX_RETRIES")
    sis_retry_backoff_base_sec: float = Field(default=0.7, alias="SIS_RETRY_BACKOFF_BASE_SEC")
    upstream_runtime_toggle_enabled: bool = Field(default=True, alias="UPSTREAM_RUNTIME_TOGGLE_ENABLED")
    upstream_redis_key: str = Field(default="ownerbot:upstream_mode", alias="UPSTREAM_REDIS_KEY")
    diagnostics_enabled: bool = Field(default=True, alias="DIAGNOSTICS_ENABLED")
    preflight_fail_fast: bool = Field(default=True, alias="PREFLIGHT_FAIL_FAST")
    shadow_check_enabled: bool = Field(default=True, alias="SHADOW_CHECK_ENABLED")
    sis_contract_check_enabled: bool = Field(default=True, alias="SIS_CONTRACT_CHECK_ENABLED")
    sizebot_base_url: str = Field(default="", alias="SIZEBOT_BASE_URL")
    sizebot_api_key: str = Field(default="", alias="SIZEBOT_API_KEY")
    sizebot_check_enabled: bool = Field(default=False, alias="SIZEBOT_CHECK_ENABLED")
    shadow_auto_on_tool_calls: bool = Field(default=False, alias="SHADOW_AUTO_ON_TOOL_CALLS")
    asr_confidence_threshold: float = Field(default=0.75, alias="ASR_CONFIDENCE_THRESHOLD")
    asr_provider: str = Field(default="mock", alias="ASR_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_asr_model: str = Field(default="gpt-4o-mini-transcribe", alias="OPENAI_ASR_MODEL")
    openai_llm_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_LLM_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com", alias="OPENAI_BASE_URL")
    llm_provider: str = Field(default="OFF", alias="LLM_PROVIDER")
    llm_timeout_seconds: int = Field(default=20, alias="LLM_TIMEOUT_SECONDS")
    llm_max_input_chars: int = Field(default=2000, alias="LLM_MAX_INPUT_CHARS")
    llm_allowed_action_tools: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["notify_team", "flag_order"], alias="LLM_ALLOWED_ACTION_TOOLS"
    )
    asr_timeout_sec: int = Field(default=20, alias="ASR_TIMEOUT_SEC")
    asr_max_retries: int = Field(default=2, alias="ASR_MAX_RETRIES")
    asr_retry_backoff_base_sec: float = Field(default=0.7, alias="ASR_RETRY_BACKOFF_BASE_SEC")
    asr_convert_format: str = Field(default="wav", alias="ASR_CONVERT_FORMAT")
    asr_convert_voice_ogg_to_wav: bool = Field(default=True, alias="ASR_CONVERT_VOICE_OGG_TO_WAV")
    asr_max_bytes: int = Field(default=20_000_000, alias="ASR_MAX_BYTES")
    asr_max_seconds: int = Field(default=180, alias="ASR_MAX_SECONDS")
    asr_prompt: str = Field(
        default="SIS, OwnerBot, OB-1003, SKU, look, reprice, publish, скидка, гривна, евро, злотый",
        alias="ASR_PROMPT",
    )
    mock_asr_text: str = Field(default="дай kpi за вчера", alias="MOCK_ASR_TEXT")
    mock_asr_confidence: float = Field(default=0.93, alias="MOCK_ASR_CONFIDENCE")
    access_deny_audit_enabled: bool = Field(default=True, alias="ACCESS_DENY_AUDIT_ENABLED")
    access_deny_audit_ttl_sec: int = Field(default=60, alias="ACCESS_DENY_AUDIT_TTL_SEC")
    access_deny_notify_once: bool = Field(default=False, alias="ACCESS_DENY_NOTIFY_ONCE")
    notify_worker_enabled: bool = Field(default=True, alias="NOTIFY_WORKER_ENABLED")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("owner_ids", mode="before")
    @classmethod
    def parse_owner_ids(cls, value: object) -> List[int]:
        return [int(v) for v in _parse_list_env(value)]

    @field_validator("manager_chat_ids", mode="before")
    @classmethod
    def parse_manager_chat_ids(cls, value: object) -> List[int]:
        return [int(v) for v in _parse_list_env(value)]

    @field_validator("llm_allowed_action_tools", mode="before")
    @classmethod
    def parse_llm_allowed_action_tools(cls, value: object) -> List[str]:
        return [str(v).strip() for v in _parse_list_env(value) if str(v).strip()]

    @model_validator(mode="after")
    def validate_owner_ids_for_non_demo(self) -> Settings:
        mode = str(self.upstream_mode).strip().upper()
        if mode != "DEMO" and not self.owner_ids:
            raise ValueError("OWNER_IDS must be configured when UPSTREAM_MODE is not DEMO.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
