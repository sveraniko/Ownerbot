from __future__ import annotations

import ast
from pathlib import Path


ROUTERS_DIR = Path("app/bot/routers")


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("app.bot.routers"):
                issues.append(f"{path}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.bot.routers"):
                    issues.append(f"{path}: import {alias.name}")
    return issues


def test_routers_do_not_import_other_routers() -> None:
    problems: list[str] = []
    for router_file in sorted(ROUTERS_DIR.glob("*.py")):
        problems.extend(_violations(router_file))
    assert not problems, "\n".join(problems)
