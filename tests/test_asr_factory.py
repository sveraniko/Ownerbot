import pytest

from app.asr.errors import ASRError
from app.asr.factory import get_asr_provider
from app.asr.mock_provider import MockASRProvider
from app.asr.openai_provider import OpenAIASRProvider
from app.core.settings import Settings


def make_settings(**overrides: object) -> Settings:
    base = {
        "bot_token": "token",
        "owner_ids": [],
        "manager_chat_ids": [],
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
    }
    base.update(overrides)
    return Settings(**base)


def test_get_asr_provider_mock() -> None:
    settings = make_settings(asr_provider="mock")
    provider = get_asr_provider(settings)
    assert isinstance(provider, MockASRProvider)


def test_get_asr_provider_openai_requires_key() -> None:
    settings = make_settings(asr_provider="openai", openai_api_key=None)
    with pytest.raises(ASRError) as exc:
        get_asr_provider(settings)
    assert exc.value.code == "BAD_CONFIG"


def test_get_asr_provider_openai() -> None:
    settings = make_settings(asr_provider="openai", openai_api_key="key")
    provider = get_asr_provider(settings)
    assert isinstance(provider, OpenAIASRProvider)
