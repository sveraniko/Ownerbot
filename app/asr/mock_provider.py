from __future__ import annotations

from app.asr.base import ASRProvider, TranscriptionResult
from app.core.settings import get_settings


class MockASRProvider(ASRProvider):
    async def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        settings = get_settings()
        return TranscriptionResult(text=settings.mock_asr_text, confidence=settings.mock_asr_confidence)
