from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import Settings


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "OWNER_IDS",
        "MANAGER_CHAT_IDS",
        "LLM_ALLOWED_ACTION_TOOLS",
        "UPSTREAM_MODE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_settings_parse_list_csv_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_IDS", " 1, 2 ,3 ")
    monkeypatch.setenv("MANAGER_CHAT_IDS", " -1001, -1002 ")
    monkeypatch.setenv("LLM_ALLOWED_ACTION_TOOLS", " notify_team, flag_order ")
    settings = Settings()

    assert settings.owner_ids == [1, 2, 3]
    assert settings.manager_chat_ids == [-1001, -1002]
    assert settings.llm_allowed_action_tools == ["notify_team", "flag_order"]


def test_settings_parse_list_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_IDS", "[1, 2]")
    monkeypatch.setenv("MANAGER_CHAT_IDS", "[-10010]")
    monkeypatch.setenv("LLM_ALLOWED_ACTION_TOOLS", '["notify_team", "flag_order"]')
    settings = Settings()

    assert settings.owner_ids == [1, 2]
    assert settings.manager_chat_ids == [-10010]
    assert settings.llm_allowed_action_tools == ["notify_team", "flag_order"]


def test_settings_parse_list_empty_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_IDS", "")
    monkeypatch.setenv("MANAGER_CHAT_IDS", "   ")
    monkeypatch.setenv("LLM_ALLOWED_ACTION_TOOLS", "")
    settings = Settings()

    assert settings.owner_ids == []
    assert settings.manager_chat_ids == []
    assert settings.llm_allowed_action_tools == []


def test_settings_non_demo_requires_owner_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTREAM_MODE", "SIS_HTTP")
    monkeypatch.setenv("OWNER_IDS", "")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_inline_comment_in_json_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_IDS", "[1,2] # comment")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_inline_comment_in_csv_non_demo_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTREAM_MODE", "SIS_HTTP")
    monkeypatch.setenv("OWNER_IDS", "# comment")

    with pytest.raises(ValidationError):
        Settings()
