import pytest

from app.asr.base import ASRProvider, TranscriptionResult
from app.asr.cache import get_or_transcribe
from app.core.redis import get_test_redis


class CountingProvider(ASRProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        self.calls += 1
        return TranscriptionResult(text="hello", confidence=0.9)


@pytest.mark.asyncio
async def test_voice_cache():
    redis_client = await get_test_redis()
    provider = CountingProvider()
    audio = b"voice-bytes"

    first = await get_or_transcribe(redis_client, provider, audio)
    second = await get_or_transcribe(redis_client, provider, audio)

    assert first.text == "hello"
    assert second.text == "hello"
    assert provider.calls == 1
