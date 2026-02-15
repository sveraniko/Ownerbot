from __future__ import annotations

from types import SimpleNamespace

import pytest


class _FakeRedis:
    def __init__(self, *, cooldown: bool = False, lock_acquired: bool = True) -> None:
        self._cooldown = cooldown
        self._lock_acquired = lock_acquired
        self._values: dict[str, str] = {}

    async def get(self, key: str):
        if "cooldown" in key and self._cooldown:
            return "1"
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx:
            if not self._lock_acquired:
                return False
            self._values[key] = value
            return True
        self._values[key] = value
        return True

    async def delete(self, key: str):
        self._values.pop(key, None)


@pytest.mark.asyncio
async def test_biz_dashboard_ops_cooldown_active_no_render(monkeypatch) -> None:
    from app.tools.impl import biz_dashboard_ops

    async def _redis():
        return _FakeRedis(cooldown=True)

    called = {"build": 0, "render": 0}

    async def _build(*args, **kwargs):
        called["build"] += 1
        return {}

    def _render(*args, **kwargs):
        called["render"] += 1
        return b"%PDF-1.4 mock"

    monkeypatch.setattr(biz_dashboard_ops, "get_redis", _redis)
    monkeypatch.setattr(biz_dashboard_ops, "build_ops_snapshot", _build)
    monkeypatch.setattr(biz_dashboard_ops, "render_ops_pdf", _render)

    res = await biz_dashboard_ops.handle(
        biz_dashboard_ops.Payload(format="pdf"),
        correlation_id="cid",
        session=object(),
        actor=SimpleNamespace(owner_user_id=1),
    )

    assert res.status == "ok"
    assert "Cooldown active" in str(res.data.get("message"))
    assert called == {"build": 0, "render": 0}


@pytest.mark.asyncio
async def test_biz_dashboard_ops_lock_not_acquired_no_render(monkeypatch) -> None:
    from app.tools.impl import biz_dashboard_ops

    async def _redis():
        return _FakeRedis(lock_acquired=False)

    called = {"build": 0, "render": 0}

    async def _build(*args, **kwargs):
        called["build"] += 1
        return {}

    def _render(*args, **kwargs):
        called["render"] += 1
        return b"%PDF-1.4 mock"

    monkeypatch.setattr(biz_dashboard_ops, "get_redis", _redis)
    monkeypatch.setattr(biz_dashboard_ops, "build_ops_snapshot", _build)
    monkeypatch.setattr(biz_dashboard_ops, "render_ops_pdf", _render)

    res = await biz_dashboard_ops.handle(
        biz_dashboard_ops.Payload(format="pdf"),
        correlation_id="cid",
        session=object(),
        actor=SimpleNamespace(owner_user_id=1),
    )

    assert res.status == "ok"
    assert "Already generating" in str(res.data.get("message"))
    assert called == {"build": 0, "render": 0}


@pytest.mark.asyncio
async def test_biz_dashboard_ops_success_returns_pdf_artifact(monkeypatch) -> None:
    from app.tools.impl import biz_dashboard_ops

    async def _redis():
        return _FakeRedis()

    async def _build(*args, **kwargs):
        return {
            "unanswered_chats": {"count": 2, "threshold_hours": 2, "top": []},
            "stuck_orders": {"count": 1, "preset": "stuck", "top": []},
            "payment_issues": {"count": 1, "preset": "payment_issues", "top": []},
            "errors": {"count": 3, "window_hours": 24, "top": []},
            "inventory": {"out_of_stock": 1, "low_stock_lte": 5, "low_stock": 2, "top_out": [], "top_low": []},
            "warnings": ["sys_last_errors:UPSTREAM_UNAVAILABLE"],
        }

    monkeypatch.setattr(biz_dashboard_ops, "get_redis", _redis)
    monkeypatch.setattr(biz_dashboard_ops, "build_ops_snapshot", _build)
    monkeypatch.setattr(biz_dashboard_ops, "render_ops_pdf", lambda *args, **kwargs: b"%PDF-1.4 mock")

    res = await biz_dashboard_ops.handle(
        biz_dashboard_ops.Payload(format="pdf"),
        correlation_id="cid",
        session=object(),
        actor=SimpleNamespace(owner_user_id=1),
    )

    assert res.status == "ok"
    assert len(res.artifacts) == 1
    assert res.artifacts[0].type == "pdf"
    assert res.artifacts[0].content
    assert "snapshot_counts" in (res.data or {})
