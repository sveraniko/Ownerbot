from __future__ import annotations

from app.asr.base import ASRProvider
from app.asr.errors import ASRError
from app.asr.mock_provider import MockASRProvider
from app.asr.openai_provider import OpenAIASRProvider
from app.core.settings import Settings


def get_asr_provider(settings: Settings) -> ASRProvider:
    provider_name = settings.asr_provider.lower()
    if provider_name == "mock":
        return MockASRProvider()
    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ASRError(code="BAD_CONFIG", message="OPENAI_API_KEY is required for ASR_PROVIDER=openai.")
        return OpenAIASRProvider(settings)
    raise ASRError(code="BAD_CONFIG", message=f"Unknown ASR_PROVIDER: {settings.asr_provider}")
