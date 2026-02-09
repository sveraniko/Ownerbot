from __future__ import annotations

import hashlib
import json

from app.asr.base import ASRProvider, TranscriptionResult


async def get_or_transcribe(redis_client, provider: ASRProvider, audio_bytes: bytes, ttl_seconds: int = 7 * 24 * 3600) -> TranscriptionResult:
    digest = hashlib.sha256(audio_bytes).hexdigest()
    key = f"voice_cache:{digest}"
    cached = await redis_client.get(key)
    if cached:
        payload = json.loads(cached)
        return TranscriptionResult(text=payload["text"], confidence=payload["confidence"])
    result = await provider.transcribe(audio_bytes)
    await redis_client.set(key, json.dumps({"text": result.text, "confidence": result.confidence}), ex=ttl_seconds)
    return result
