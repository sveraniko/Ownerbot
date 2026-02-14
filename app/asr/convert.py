from __future__ import annotations

from typing import Tuple

from app.asr.audio_convert import convert_ogg_to_wav
from app.asr.errors import AudioConvertError

SUPPORTED_FORMATS = {
    "wav": "audio/wav",
    "webm": "audio/webm",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
}


def detect_audio_format(audio_bytes: bytes) -> str | None:
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b"OggS":
        return "ogg"
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "wav"
    if len(audio_bytes) >= 3 and audio_bytes[:3] == b"ID3":
        return "mp3"
    if len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return "mp3"
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if b"ftyp" in audio_bytes[:32]:
        return "m4a"
    return None


def convert_telegram_voice(audio_bytes: bytes, target: str = "wav") -> Tuple[bytes, str]:
    target_format = target.lower()
    if target_format not in SUPPORTED_FORMATS:
        raise AudioConvertError("Unsupported audio format.")

    detected = detect_audio_format(audio_bytes)
    if detected == "ogg":
        if target_format != "wav":
            raise AudioConvertError("Only wav target is supported for ogg conversion.")
        return convert_ogg_to_wav(audio_bytes), "wav"

    if detected in SUPPORTED_FORMATS:
        return audio_bytes, detected

    raise AudioConvertError("Unsupported audio format.")
