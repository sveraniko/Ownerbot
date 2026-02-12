from __future__ import annotations

import asyncio

from app.llm.provider_mock import MockPlanner


def test_mock_planner_chart_intent() -> None:
    planner = MockPlanner()

    intent = asyncio.run(planner.plan("график выручки 14 дней"))

    assert intent.tool == "revenue_trend"
    assert intent.payload.get("days") == 14
    assert intent.presentation == {"kind": "chart_png", "days": 14}


def test_mock_planner_weekly_preset() -> None:
    planner = MockPlanner()

    intent = asyncio.run(planner.plan("сделай недельный pdf отчет"))

    assert intent.tool == "weekly_preset"
    assert intent.payload == {}


def test_mock_planner_action_payload_is_dry_run() -> None:
    planner = MockPlanner()

    intent = asyncio.run(planner.plan("уведомь команду: проверь зависшие заказы"))

    assert intent.tool == "notify_team"
    assert intent.payload.get("dry_run") is True
