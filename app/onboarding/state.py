from __future__ import annotations

from app.core.time import utcnow
from app.storage.models import OwnerNotifySettings

_ALLOWED_STATUS = {"ok", "warn", "fail"}


def apply_onboard_run_result(
    settings: OwnerNotifySettings,
    *,
    status: str,
    summary: str,
    mark_completed: bool,
) -> None:
    now = utcnow()
    settings.onboard_last_run_at = now
    settings.onboard_last_status = status if status in _ALLOWED_STATUS else "warn"
    settings.onboard_last_summary = (summary or "")[:200] or None
    if mark_completed and settings.onboard_completed_at is None:
        settings.onboard_completed_at = now
