import subprocess

import pytest

from app.asr.convert import convert_telegram_voice
from app.asr.errors import AudioConvertError


def test_convert_telegram_voice_success(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["ffmpeg"], returncode=0, stdout=b"wav-bytes", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    output, ext = convert_telegram_voice(b"voice", target="wav")

    assert output == b"wav-bytes"
    assert ext == "wav"


def test_convert_telegram_voice_missing_ffmpeg(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(AudioConvertError):
        convert_telegram_voice(b"voice", target="wav")
