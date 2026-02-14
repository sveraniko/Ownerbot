from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl.notify_team import Payload, _render_message, handle


@pytest.mark.asyncio
async def test_notify_team_dry_run_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tools.impl.notify_team.get_settings",
        lambda: SimpleNamespace(manager_chat_ids=[-1001, 2002]),
    )
    payload = Payload(message="Проверь заказы", dry_run=True)

    response = await handle(payload, "corr-1", session=None, actor=ToolActor(owner_user_id=77))

    assert response.status == "ok"
    assert response.data["dry_run"] is True
    assert response.data["recipients"] == [-1001, 2002]
    assert "Проверь заказы" in response.data["message_preview"]
    assert "corr-1" in response.data["message_preview"]
    assert response.provenance.sources


@pytest.mark.asyncio
async def test_notify_team_missing_manager_chat_ids_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tools.impl.notify_team.get_settings",
        lambda: SimpleNamespace(manager_chat_ids=[]),
    )
    payload = Payload(message="Проверь заказы", dry_run=True)

    response = await handle(payload, "corr-2", session=None, actor=ToolActor(owner_user_id=1))

    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "CONFIG_MISSING"


@pytest.mark.asyncio
async def test_notify_team_commit_calls_send_message_for_each_recipient(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tools.impl.notify_team.get_settings",
        lambda: SimpleNamespace(manager_chat_ids=[10, 20]),
    )
    bot = AsyncMock()
    payload = Payload(message="Проверь заказы", dry_run=False)
    actor = ToolActor(owner_user_id=1)
    expected_message = _render_message(payload.message, "corr-3", actor)

    response = await handle(payload, "corr-3", session=None, actor=actor, bot=bot)

    assert response.status == "ok"
    bot.send_message.assert_has_awaits(
        [
            call(chat_id=10, text=expected_message, disable_notification=False),
            call(chat_id=20, text=expected_message, disable_notification=False),
        ]
    )


@pytest.mark.asyncio
async def test_notify_team_partial_delivery_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tools.impl.notify_team.get_settings",
        lambda: SimpleNamespace(manager_chat_ids=[1, 2]),
    )

    async def send_message(*, chat_id: int, text: str, disable_notification: bool) -> None:
        if chat_id == 2:
            raise RuntimeError("boom")

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
    payload = Payload(message="Проверь заказы", dry_run=False)

    response = await handle(payload, "corr-4", session=None, actor=ToolActor(owner_user_id=1), bot=bot)

    assert response.status == "ok"
    assert response.warnings
    assert response.warnings[0].code == "PARTIAL_DELIVERY"
    assert response.data["sent"] == [1]
    assert response.data["failed"][0]["chat_id"] == 2


@pytest.mark.asyncio
async def test_run_tool_passes_bot_when_needed() -> None:
    from app.bot.services.tool_runner import run_tool

    received = {}
    bot_marker = object()

    async def handler(payload, correlation_id: str, session, actor: ToolActor, bot) -> ToolResponse:
        received["bot"] = bot
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={},
            provenance=ToolProvenance(sources=["local"]),
        )

    class DummyPayload:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    tool = SimpleNamespace(name="dummy", payload_model=DummyPayload, handler=handler)
    registry = SimpleNamespace(get=lambda _: tool)

    class DummyScope:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    message = SimpleNamespace(bot=bot_marker)
    response = await run_tool(
        "dummy",
        {},
        message=message,
        actor=ToolActor(owner_user_id=1),
        tenant=SimpleNamespace(),
        correlation_id="corr-5",
        session_factory=lambda: DummyScope(),
        registry=registry,
    )

    assert response.status == "ok"
    assert received["bot"] is bot_marker


@pytest.mark.asyncio
async def test_run_tool_passes_idempotency_key_when_handler_accepts_it() -> None:
    from app.bot.services.tool_runner import run_tool

    received = {}

    async def handler(payload, correlation_id: str, session, idempotency_key: str | None = None) -> ToolResponse:
        received["idempotency_key"] = idempotency_key
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={},
            provenance=ToolProvenance(sources=["local"]),
        )

    class DummyPayload:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    tool = SimpleNamespace(name="dummy", payload_model=DummyPayload, handler=handler)
    registry = SimpleNamespace(get=lambda _: tool)

    class DummyScope:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    response = await run_tool(
        "dummy",
        {},
        actor=ToolActor(owner_user_id=1),
        tenant=SimpleNamespace(),
        correlation_id="corr-6",
        idempotency_key="idem-777",
        session_factory=lambda: DummyScope(),
        registry=registry,
    )

    assert response.status == "ok"
    assert received["idempotency_key"] == "idem-777"
