from __future__ import annotations

from pathlib import Path


def test_home_ui_contains_focus_callbacks() -> None:
    source = Path("app/bot/routers/home_ui.py").read_text(encoding="utf-8")
    assert 'F.data == "ui:focus:burn"' in source
    assert 'F.data == "ui:focus:money"' in source
    assert 'F.data == "ui:focus:stock"' in source
