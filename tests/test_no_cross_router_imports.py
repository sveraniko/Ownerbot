import ast
from pathlib import Path


def test_actions_router_has_no_owner_console_import() -> None:
    actions_path = Path("app/bot/routers/actions.py")
    module = ast.parse(actions_path.read_text())

    imported_modules = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    assert "app.bot.routers.owner_console" not in imported_modules
