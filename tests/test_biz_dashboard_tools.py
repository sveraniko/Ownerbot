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
async def test_biz_dashboard_daily_lock_not_acquired_skips_render(monkeypatch) -> None:
    from app.tools.impl import biz_dashboard_daily

    async def _redis():
        return _FakeRedis(lock_acquired=False)

    called = {"build": 0}

    async def _build(*args, **kwargs):
        called["build"] += 1
        return SimpleNamespace(text="x", warnings=[], series=[])

    monkeypatch.setattr(biz_dashboard_daily, "get_redis", _redis)
    monkeypatch.setattr(biz_dashboard_daily, "build_daily_digest", _build)

    res = await biz_dashboard_daily.handle(
        biz_dashboard_daily.Payload(format="png"),
        correlation_id="cid",
        session=object(),
        actor=SimpleNamespace(owner_user_id=10),
    )

    assert res.status == "ok"
    assert called["build"] == 0
    assert "Already generating" in str(res.data.get("message"))


@pytest.mark.asyncio
async def test_biz_dashboard_daily_cooldown_skips_render(monkeypatch) -> None:
    from app.tools.impl import biz_dashboard_daily

    async def _redis():
        return _FakeRedis(cooldown=True)

    called = {"build": 0}

    async def _build(*args, **kwargs):
        called["build"] += 1
        return SimpleNamespace(text="x", warnings=[], series=[])

    monkeypatch.setattr(biz_dashboard_daily, "get_redis", _redis)
    monkeypatch.setattr(biz_dashboard_daily, "build_daily_digest", _build)

    res = await biz_dashboard_daily.handle(
        biz_dashboard_daily.Payload(format="png"),
        correlation_id="cid",
        session=object(),
        actor=SimpleNamespace(owner_user_id=10),
    )

    assert res.status == "ok"
    assert called["build"] == 0
    assert "Cooldown active" in str(res.data.get("message"))


@pytest.mark.asyncio
async def test_biz_dashboard_weekly_returns_pdf_artifact(monkeypatch) -> None:
    from app.tools.impl import biz_dashboard_weekly

    async def _redis():
        return _FakeRedis()

    async def _build(*args, **kwargs):
        return SimpleNamespace(text="weekly", warnings=["warn"], series=[], kpi_summary={}, ops_summary={}, fx_summary={})

    monkeypatch.setattr(biz_dashboard_weekly, "get_redis", _redis)
    monkeypatch.setattr(biz_dashboard_weekly, "build_weekly_digest", _build)
    monkeypatch.setattr(biz_dashboard_weekly, "render_weekly_pdf", lambda bundle: b"%PDF-1.4 mock")

    res = await biz_dashboard_weekly.handle(
        biz_dashboard_weekly.Payload(format="pdf"),
        correlation_id="cid",
        session=object(),
        actor=SimpleNamespace(owner_user_id=10),
    )

    assert res.status == "ok"
    assert len(res.artifacts) == 1
    assert res.artifacts[0].type == "pdf"
    assert res.artifacts[0].content
