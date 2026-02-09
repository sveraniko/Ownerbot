from __future__ import annotations

from app.core.settings import get_settings


def is_owner(user_id: int) -> bool:
    settings = get_settings()
    return user_id in settings.owner_ids
