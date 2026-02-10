from __future__ import annotations

import subprocess
from typing import Tuple

from app.asr.errors import AudioConvertError

SUPPORTED_FORMATS = {"wav": "audio/wav", "webm": "audio/webm"}


def convert_telegram_voice(audio_bytes: bytes, target: str = "wav") -> Tuple[bytes, str]:
    target_format = target.lower()
    if target_format not in SUPPORTED_FORMATS:
        raise AudioConvertError("Unsupported audio format.")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-f",
        target_format,
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            command,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise AudioConvertError("ffmpeg is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioConvertError("Audio conversion timed out.") from exc

    if result.returncode != 0 or not result.stdout:
        raise AudioConvertError("Audio conversion failed.")

    return result.stdout, target_format
