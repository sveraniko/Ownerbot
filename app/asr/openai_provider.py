from __future__ import annotations

import asyncio

import httpx

from app.asr.base import ASRProvider, TranscriptionResult
from app.asr.convert import SUPPORTED_FORMATS, convert_telegram_voice
from app.asr.errors import ASRError, AudioConvertError
from app.core.settings import Settings


class OpenAIASRProvider(ASRProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        try:
            converted_bytes, ext = convert_telegram_voice(audio_bytes, target=self._settings.asr_convert_format)
        except AudioConvertError:
            raise

        mime_type = SUPPORTED_FORMATS[ext]
        url = f"{self._settings.openai_base_url.rstrip('/')}/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self._settings.openai_api_key}"}
        data = {"model": self._settings.openai_asr_model, "response_format": "json"}
        if self._settings.asr_prompt:
            data["prompt"] = self._settings.asr_prompt
        files = {"file": (f"voice.{ext}", converted_bytes, mime_type)}
        timeout = httpx.Timeout(self._settings.asr_timeout_sec)

        max_retries = max(0, self._settings.asr_max_retries)
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, headers=headers, data=data, files=files)
            except httpx.RequestError as exc:
                raise ASRError(code="UPSTREAM_UNAVAILABLE", message="ASR upstream unavailable.") from exc

            status = response.status_code
            if status == 200:
                payload = response.json()
                text = str(payload.get("text", "")).strip()
                confidence = 0.0 if not text else 0.9
                return TranscriptionResult(text=text, confidence=confidence)

            if status in (401, 403):
                raise ASRError(code="BAD_CONFIG", message="Invalid OpenAI credentials.")

            if status == 429 or status >= 500:
                if attempt < max_retries:
                    backoff = self._settings.asr_retry_backoff_base_sec * (2**attempt)
                    await asyncio.sleep(backoff)
                    continue
                raise ASRError(code="UPSTREAM_UNAVAILABLE", message="ASR upstream unavailable.")

            raise ASRError(code="ASR_FAILED", message="ASR request failed.")

        raise ASRError(code="UPSTREAM_UNAVAILABLE", message="ASR upstream unavailable.")
