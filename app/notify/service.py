from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notify.engine import (
    clamp_float,
    clamp_int,
    normalize_digest_format,
    normalize_weekly_day_of_week,
    parse_time_local_or_default,
)
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
    async def set_fx_apply_events(
        session: AsyncSession,
        owner_id: int,
        *,
        enabled: bool,
        notify_applied: bool | None = None,
        notify_noop: bool | None = None,
        notify_failed: bool | None = None,
        cooldown_hours: int | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.fx_apply_events_enabled = enabled
        if notify_applied is not None:
            settings.fx_apply_notify_applied = notify_applied
        if notify_noop is not None:
            settings.fx_apply_notify_noop = notify_noop
        if notify_failed is not None:
            settings.fx_apply_notify_failed = notify_failed
        if cooldown_hours is not None:
            settings.fx_apply_events_cooldown_hours = max(1, min(int(cooldown_hours), 168))
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
            hh, mm = parse_time_local_or_default(time_local)
            settings.digest_time_local = f"{hh:02d}:{mm:02d}"
        if tz is not None:
            settings.digest_tz = tz
            if not settings.weekly_tz:
                settings.weekly_tz = tz
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def set_digest_format(session: AsyncSession, owner_id: int, *, digest_format: str) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.digest_format = normalize_digest_format(digest_format)
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def set_weekly(
        session: AsyncSession,
        owner_id: int,
        *,
        enabled: bool,
        day_of_week: int | None = None,
        time_local: str | None = None,
        tz: str | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.weekly_enabled = enabled
        if day_of_week is not None:
            settings.weekly_day_of_week = normalize_weekly_day_of_week(day_of_week)
        if time_local is not None:
            hh, mm = parse_time_local_or_default(time_local, default=(9, 30))
            settings.weekly_time_local = f"{hh:02d}:{mm:02d}"
        if tz is not None:
            settings.weekly_tz = tz
        elif not settings.weekly_tz:
            settings.weekly_tz = settings.digest_tz
        await session.commit()
        await session.refresh(settings)
        return settings


    @staticmethod
    async def set_ops_alerts(
        session: AsyncSession,
        owner_id: int,
        *,
        enabled: bool,
        cooldown_hours: int | None = None,
        rules: dict[str, object] | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.ops_alerts_enabled = enabled
        if cooldown_hours is not None:
            settings.ops_alerts_cooldown_hours = max(1, min(int(cooldown_hours), 168))

        rules = rules or {}
        for attr, value in rules.items():
            if hasattr(settings, attr) and value is not None:
                setattr(settings, attr, value)

        await session.commit()
        await session.refresh(settings)
        return settings


    @staticmethod
    async def set_digest_quiet_mode(
        session: AsyncSession,
        owner_id: int,
        *,
        enabled: bool,
        attempt_interval_minutes: int | None = None,
        max_silence_days: int | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.digest_quiet_enabled = enabled
        if attempt_interval_minutes is not None:
            settings.digest_quiet_attempt_interval_minutes = clamp_int(attempt_interval_minutes, min_value=15, max_value=360)
        if max_silence_days is not None:
            settings.digest_quiet_max_silence_days = clamp_int(max_silence_days, min_value=1, max_value=30)
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def set_digest_quiet_rules(
        session: AsyncSession,
        owner_id: int,
        *,
        min_revenue_drop_pct: float | None = None,
        min_orders_drop_pct: float | None = None,
        send_on_ops: bool | None = None,
        send_on_fx_failed: bool | None = None,
        send_on_errors: bool | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        if min_revenue_drop_pct is not None:
            settings.digest_quiet_min_revenue_drop_pct = clamp_float(min_revenue_drop_pct, min_value=0.1, max_value=50.0)
        if min_orders_drop_pct is not None:
            settings.digest_quiet_min_orders_drop_pct = clamp_float(min_orders_drop_pct, min_value=0.1, max_value=50.0)
        if send_on_ops is not None:
            settings.digest_quiet_send_on_ops = bool(send_on_ops)
        if send_on_fx_failed is not None:
            settings.digest_quiet_send_on_fx_failed = bool(send_on_fx_failed)
        if send_on_errors is not None:
            settings.digest_quiet_send_on_errors = bool(send_on_errors)
        await session.commit()
        await session.refresh(settings)
        return settings


    @staticmethod
    async def set_escalation_enabled(session: AsyncSession, owner_id: int, *, enabled: bool) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        settings.escalation_enabled = bool(enabled)
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def set_escalation_rules(
        session: AsyncSession,
        owner_id: int,
        *,
        stage1_after_minutes: int | None = None,
        repeat_every_minutes: int | None = None,
        max_repeats: int | None = None,
        escalation_on_fx_failed: bool | None = None,
        escalation_on_out_of_stock: bool | None = None,
        escalation_on_stuck_orders_severe: bool | None = None,
        escalation_on_errors_spike: bool | None = None,
        escalation_on_unanswered_chats_severe: bool | None = None,
        escalation_stuck_orders_min: int | None = None,
        escalation_errors_min: int | None = None,
        escalation_unanswered_chats_min: int | None = None,
        escalation_unanswered_threshold_hours: int | None = None,
    ) -> OwnerNotifySettings:
        settings = await NotificationSettingsService.get_or_create(session, owner_id)
        if stage1_after_minutes is not None:
            settings.escalation_stage1_after_minutes = clamp_int(stage1_after_minutes, min_value=30, max_value=1440)
        if repeat_every_minutes is not None:
            settings.escalation_repeat_every_minutes = clamp_int(repeat_every_minutes, min_value=60, max_value=2880)
        if max_repeats is not None:
            settings.escalation_max_repeats = clamp_int(max_repeats, min_value=0, max_value=10)

        for attr, value in {
            "escalation_on_fx_failed": escalation_on_fx_failed,
            "escalation_on_out_of_stock": escalation_on_out_of_stock,
            "escalation_on_stuck_orders_severe": escalation_on_stuck_orders_severe,
            "escalation_on_errors_spike": escalation_on_errors_spike,
            "escalation_on_unanswered_chats_severe": escalation_on_unanswered_chats_severe,
        }.items():
            if value is not None:
                setattr(settings, attr, bool(value))

        if escalation_stuck_orders_min is not None:
            settings.escalation_stuck_orders_min = clamp_int(escalation_stuck_orders_min, min_value=0, max_value=999)
        if escalation_errors_min is not None:
            settings.escalation_errors_min = clamp_int(escalation_errors_min, min_value=0, max_value=999)
        if escalation_unanswered_chats_min is not None:
            settings.escalation_unanswered_chats_min = clamp_int(escalation_unanswered_chats_min, min_value=0, max_value=999)
        if escalation_unanswered_threshold_hours is not None:
            settings.escalation_unanswered_threshold_hours = clamp_int(escalation_unanswered_threshold_hours, min_value=1, max_value=168)

        await session.commit()
        await session.refresh(settings)
        return settings
