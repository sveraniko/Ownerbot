from app.bot.main import build_dispatcher
from app.bot.routers import menu, owner_console


def test_menu_router_registered_before_owner_console() -> None:
    dispatcher = build_dispatcher()

    menu_idx = dispatcher.sub_routers.index(menu.router)
    owner_console_idx = dispatcher.sub_routers.index(owner_console.router)

    assert menu_idx < owner_console_idx
