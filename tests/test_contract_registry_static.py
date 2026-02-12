from __future__ import annotations

from pathlib import Path
import re


def test_required_action_tools_registered_non_stub() -> None:
    source = Path("app/tools/registry_setup.py").read_text(encoding="utf-8")

    assert re.search(r'register\("notify_team"[\s\S]*?is_stub\s*=\s*False[\s\S]*?kind\s*=\s*"action"', source)

    assert re.search(r'register\("flag_order"[\s\S]*?kind\s*=\s*"action"', source)


def test_required_read_tools_exist() -> None:
    source = Path("app/tools/registry_setup.py").read_text(encoding="utf-8")
    for tool_name in ("kpi_snapshot", "orders_search", "order_detail"):
        assert f'register("{tool_name}"' in source
