from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(alias="BOT_TOKEN")
    owner_ids: List[int] = Field(default_factory=list, alias="OWNER_IDS")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    upstream_mode: str = Field(default="DEMO", alias="UPSTREAM_MODE")
    asr_confidence_threshold: float = Field(default=0.75, alias="ASR_CONFIDENCE_THRESHOLD")
    mock_asr_text: str = Field(default="дай kpi за вчера", alias="MOCK_ASR_TEXT")
    mock_asr_confidence: float = Field(default=0.93, alias="MOCK_ASR_CONFIDENCE")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
