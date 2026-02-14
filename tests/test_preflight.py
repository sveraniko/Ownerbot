from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.preflight import preflight_validate_settings


def _settings(**overrides):
    base = {
        "bot_token": "token",
        "owner_ids": [1],
        "upstream_mode": "DEMO",
        "asr_provider": "mock",
        "llm_provider": "OFF",
        "openai_api_key": "",
        "asr_convert_voice_ogg_to_wav": False,
        "sis_base_url": "",
        "sis_ownerbot_api_key": "",
        "sizebot_check_enabled": False,
        "sizebot_base_url": "",
        "sizebot_api_key": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_preflight_bot_token_missing() -> None:
    report = preflight_validate_settings(_settings(bot_token=""))
    assert report.ok is False
    assert any(item.code == "BOT_TOKEN_MISSING" for item in report.items)


def test_preflight_owner_ids_missing() -> None:
    report = preflight_validate_settings(_settings(owner_ids=[]))
    assert report.ok is False
    assert any(item.code == "OWNER_IDS_MISSING" for item in report.items)


def test_preflight_openai_asr_requires_key() -> None:
    report = preflight_validate_settings(_settings(asr_provider="openai", openai_api_key=""))
    assert any(item.code == "OPENAI_KEY_MISSING" for item in report.items)


def test_preflight_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    report = preflight_validate_settings(_settings(asr_convert_voice_ogg_to_wav=True))
    assert any(item.code == "FFMPEG_MISSING" for item in report.items)


def test_preflight_fail_fast_flag_does_not_change_report() -> None:
    report_true = preflight_validate_settings(_settings(bot_token=""))
    report_false = preflight_validate_settings(_settings(bot_token=""))
    assert report_true.ok == report_false.ok
    assert [item.code for item in report_true.items] == [item.code for item in report_false.items]
