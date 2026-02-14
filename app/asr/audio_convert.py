from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.asr.errors import AudioConvertError


FFMPEG_TIMEOUT_SECONDS = 20


def convert_ogg_to_wav(ogg_bytes: bytes) -> bytes:
    ogg_path: Path | None = None
    wav_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as src:
            src.write(ogg_bytes)
            ogg_path = Path(src.name)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as dst:
            wav_path = Path(dst.name)

        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(ogg_path),
                str(wav_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise AudioConvertError("ffmpeg is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioConvertError("Audio conversion timed out.") from exc
    finally:
        if ogg_path and ogg_path.exists():
            ogg_path.unlink(missing_ok=True)

    if result.returncode != 0 or wav_path is None or not wav_path.exists() or wav_path.stat().st_size == 0:
        if wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)
        raise AudioConvertError("Audio conversion failed.")

    wav_bytes = wav_path.read_bytes()
    wav_path.unlink(missing_ok=True)
    return wav_bytes
