from __future__ import annotations

from pathlib import Path

from app.core import contracts


def test_callback_contract_constants() -> None:
    assert contracts.CONFIRM_CB_PREFIX == "confirm:"
    assert contracts.CANCEL_CB_PREFIX == "cancel:"
    assert contracts.CONFIRM_TOKEN_RETAIN_TTL_SEC_DEFAULT > 0


def test_actions_router_uses_callback_prefix_constants() -> None:
    source = Path("app/bot/routers/actions.py").read_text(encoding="utf-8")
    assert "F.data.startswith(CONFIRM_CB_PREFIX)" in source
    assert "F.data.startswith(CANCEL_CB_PREFIX)" in source
    assert "split(CONFIRM_CB_PREFIX, 1)" in source
    assert "split(CANCEL_CB_PREFIX, 1)" in source
