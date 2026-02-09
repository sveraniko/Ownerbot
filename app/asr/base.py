from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    text: str
    confidence: float


class ASRProvider:
    async def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        raise NotImplementedError
