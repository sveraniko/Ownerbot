import httpx
import pytest

from app.asr.openai_provider import OpenAIASRProvider
from app.core.settings import Settings


class FakeClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, data=None, files=None):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_settings(**overrides: object) -> Settings:
    base = {
        "bot_token": "token",
        "owner_ids": [],
        "manager_chat_ids": [],
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "asr_provider": "openai",
        "openai_api_key": "key",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_openai_asr_success(monkeypatch) -> None:
    responses = [httpx.Response(200, json={"text": "привет"})]
    client = FakeClient(responses)

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.asr.openai_provider.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("app.asr.openai_provider.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "app.asr.openai_provider.convert_telegram_voice",
        lambda audio_bytes, target: (b"wavbytes", "wav"),
    )

    provider = OpenAIASRProvider(make_settings())
    result = await provider.transcribe(b"voice")

    assert result.text == "привет"
    assert result.confidence == 0.9
    assert client.calls == 1


@pytest.mark.asyncio
async def test_openai_asr_retries_on_429(monkeypatch) -> None:
    responses = [
        httpx.Response(429, json={"error": {"message": "rate limit"}}),
        httpx.Response(200, json={"text": "ok"}),
    ]
    client = FakeClient(responses)

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.asr.openai_provider.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("app.asr.openai_provider.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "app.asr.openai_provider.convert_telegram_voice",
        lambda audio_bytes, target: (b"wavbytes", "wav"),
    )

    settings = make_settings(asr_max_retries=2)
    provider = OpenAIASRProvider(settings)
    result = await provider.transcribe(b"voice")

    assert result.text == "ok"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_openai_asr_retries_on_500(monkeypatch) -> None:
    responses = [
        httpx.Response(500, json={"error": {"message": "boom"}}),
        httpx.Response(200, json={"text": "ok"}),
    ]
    client = FakeClient(responses)

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.asr.openai_provider.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("app.asr.openai_provider.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "app.asr.openai_provider.convert_telegram_voice",
        lambda audio_bytes, target: (b"wavbytes", "wav"),
    )

    settings = make_settings(asr_max_retries=1)
    provider = OpenAIASRProvider(settings)
    result = await provider.transcribe(b"voice")

    assert result.text == "ok"
    assert client.calls == 2
