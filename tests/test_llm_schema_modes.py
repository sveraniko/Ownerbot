from __future__ import annotations

import pytest

from app.llm.schema import LLMIntent


def test_llm_schema_tool_mode_parses() -> None:
    intent = LLMIntent.model_validate(
        {
            "intent_kind": "TOOL",
            "tool": "notify_team",
            "payload": {"message": "ping", "dry_run": True},
            "presentation": None,
            "advice": None,
            "error_message": None,
            "confidence": 0.8,
        }
    )
    assert intent.intent_kind == "TOOL"
    assert intent.tool == "notify_team"


def test_llm_schema_advice_mode_parses() -> None:
    intent = LLMIntent.model_validate(
        {
            "intent_kind": "ADVICE",
            "tool": None,
            "payload": {},
            "presentation": None,
            "advice": {
                "bullets": ["Проверьте каналы"],
                "experiments": ["Сегментировать трафик"],
                "suggested_tools": [{"tool": "kpi_snapshot", "payload": {"window": "7d"}}],
            },
            "error_message": None,
            "confidence": 0.5,
        }
    )
    assert intent.intent_kind == "ADVICE"
    assert intent.advice is not None
    assert intent.advice.suggested_tools[0].tool == "kpi_snapshot"


def test_llm_schema_unknown_requires_error_message() -> None:
    with pytest.raises(Exception):
        LLMIntent.model_validate(
            {
                "intent_kind": "UNKNOWN",
                "tool": None,
                "payload": {},
                "presentation": None,
                "advice": None,
                "error_message": None,
                "confidence": 0.0,
            }
        )
