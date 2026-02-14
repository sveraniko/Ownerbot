import subprocess
from pathlib import Path

import pytest

from app.asr.audio_convert import convert_ogg_to_wav
from app.asr.convert import convert_telegram_voice
from app.asr.errors import AudioConvertError


def test_convert_ogg_to_wav_runs_ffmpeg_and_cleans_tmp(monkeypatch, tmp_path: Path) -> None:
    created_paths: list[Path] = []

    class _FakeTempFile:
        def __init__(self, suffix: str):
            idx = len(created_paths)
            self.name = str(tmp_path / f"tmp_{idx}{suffix}")
            created_paths.append(Path(self.name))
            Path(self.name).write_bytes(b"")

        def write(self, data: bytes) -> None:
            Path(self.name).write_bytes(data)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_named_tempfile(*, suffix: str, delete: bool = False):
        return _FakeTempFile(suffix)

    def fake_run(cmd, **_kwargs):
        assert cmd[0] == "ffmpeg"
        assert cmd[6].endswith(".ogg")
        assert cmd[7].endswith(".wav")
        Path(cmd[7]).write_bytes(b"wav-bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.asr.audio_convert.tempfile.NamedTemporaryFile", fake_named_tempfile)
    monkeypatch.setattr(subprocess, "run", fake_run)

    output = convert_ogg_to_wav(b"OggS-data")

    assert output == b"wav-bytes"
    assert all(not p.exists() for p in created_paths)


def test_convert_telegram_voice_ogg_to_wav(monkeypatch) -> None:
    monkeypatch.setattr("app.asr.convert.convert_ogg_to_wav", lambda _audio: b"wav")

    out, ext = convert_telegram_voice(b"OggSraw", target="wav")

    assert out == b"wav"
    assert ext == "wav"


def test_convert_telegram_voice_rejects_unknown() -> None:
    with pytest.raises(AudioConvertError):
        convert_telegram_voice(b"unknown", target="wav")
