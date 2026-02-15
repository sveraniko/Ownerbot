from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import OwnerNotifySettings


class NotificationSettingsService:
    @staticmethod
    async def get_or_create(session: AsyncSession, owner_id: int) -> OwnerNotifySettings:
        row = await session.scalar(select(OwnerNotifySettings).where(OwnerNotifySettings.owner_id == owner_id))
        if row is not None:
            return row
        row = OwnerNotifySettings(owner_id=owner_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @staticmethod
    async def set_fx_delta(
        session: AsyncSession,
        owner_id: int,
        *,
        enabled: bool,
        min_percent: float | None = None,
        cooldown_hours: int | None = None,
        last_notified_rate: float | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.fx_delta_enabled = enabled
        if min_percent is not None:
            settings.fx_delta_min_percent = min_percent
        if cooldown_hours is not None:
            settings.fx_delta_cooldown_hours = cooldown_hours
        if last_notified_rate is not None:
            settings.fx_delta_last_notified_rate = last_notified_rate
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def set_digest(
        session: AsyncSession,
        owner_id: int,
        *,
        enabled: bool,
        time_local: str | None = None,
        tz: str | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.digest_enabled = enabled
        if time_local is not None:
            settings.digest_time_local = time_local
        if tz is not None:
            settings.digest_tz = tz
        await session.commit()
        await session.refresh(settings)
        return settings
