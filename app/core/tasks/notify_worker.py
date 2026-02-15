from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.core.audit import write_audit_event
from app.core.db import session_scope
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.notify import NotificationSettingsService, extract_fx_rate_and_schedule, should_send_digest, should_send_fx_delta
from app.tools.impl import sis_fx_status


@dataclass
class LockResult:
    acquired: bool
    token: str


class NotifyWorker:
    CHECK_INTERVAL_SECONDS = 300
    LOCK_KEY = "ownerbot:notify:lock"
    LOCK_TTL_SECONDS = 900

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._stopped = False
        self._chat_last_send_ts: dict[int, float] = {}

    async def run_forever(self) -> None:
        while not self._stopped:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await write_audit_event("notify_error", {"stage": "tick", "message": str(exc)[:200]})
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    async def tick(self) -> None:
        lock = await self._acquire_lock()
        if not lock.acquired:
            return
        try:
            settings = get_settings()
            for owner_id in settings.owner_ids:
                await self._process_owner(owner_id)
        finally:
            await self._release_lock(lock.token)

    async def _process_owner(self, owner_id: int) -> None:
        async with session_scope() as session:
            notify_settings = await NotificationSettingsService.get_or_create(session, owner_id)

            if notify_settings.fx_delta_enabled:
                await self._maybe_send_fx_delta(owner_id, notify_settings, session)

            if notify_settings.digest_enabled:
                await self._maybe_send_digest(owner_id, notify_settings, session)

    async def _maybe_send_fx_delta(self, owner_id: int, notify_settings, session) -> None:
        now = datetime.now(timezone.utc)
        try:
            payload = sis_fx_status.Payload()
            response = await sis_fx_status.handle(payload, correlation_id=f"notify-fx-{owner_id}", session=session)
            if response.status != "ok":
                await self._notify_error_with_cooldown(notify_settings, session, owner_id, "fx_status_error")
                return
            snapshot = extract_fx_rate_and_schedule(response.data)
            if not should_send_fx_delta(
                now=now,
                last_rate=float(notify_settings.fx_delta_last_notified_rate) if notify_settings.fx_delta_last_notified_rate else None,
                new_rate=snapshot.effective_rate,
                min_percent=float(notify_settings.fx_delta_min_percent),
                last_notified_at=notify_settings.fx_delta_last_notified_at,
                cooldown_hours=int(notify_settings.fx_delta_cooldown_hours),
            ):
                return

            old_rate = float(notify_settings.fx_delta_last_notified_rate or snapshot.effective_rate or 0)
            new_rate = float(snapshot.effective_rate or 0)
            delta_pct = ((new_rate - old_rate) / old_rate * 100) if old_rate else 0.0
            message = f"🔔 FX delta: {old_rate:.4f} → {new_rate:.4f} ({delta_pct:+.2f}%)"
            sent = await self._safe_send(owner_id, message)
            if not sent:
                return

            notify_settings.fx_delta_last_notified_rate = new_rate
            notify_settings.fx_delta_last_notified_at = now
            for key in ("last_apply_success_at", "last_apply_attempt_at", "last_apply_failed_at"):
                value = snapshot.schedule_fields.get(key)
                if isinstance(value, str) and value:
                    notify_settings.fx_delta_last_seen_sis_event_at = now
                    break
            await session.commit()
            await write_audit_event("notify_fx_delta_sent", {"owner_id": owner_id, "rate": new_rate, "delta_pct": round(delta_pct, 3)})
        except Exception as exc:
            await self._notify_error_with_cooldown(notify_settings, session, owner_id, f"fx_delta_failed:{str(exc)[:120]}")

    async def _maybe_send_digest(self, owner_id: int, notify_settings, session) -> None:
        now_utc = datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(str(notify_settings.digest_tz))
        except Exception:
            tz = ZoneInfo("Europe/Berlin")
        now_local = now_utc.astimezone(tz)
        last_sent_local = notify_settings.digest_last_sent_at.astimezone(tz) if notify_settings.digest_last_sent_at else None
        if not should_send_digest(now_local=now_local, last_sent_at=last_sent_local, digest_time_local=notify_settings.digest_time_local):
            return

        payload = sis_fx_status.Payload()
        fx_response = await sis_fx_status.handle(payload, correlation_id=f"notify-digest-{owner_id}", session=session)
        fx_line = "FX: N/A"
        if fx_response.status == "ok":
            snapshot = extract_fx_rate_and_schedule(fx_response.data)
            if snapshot.effective_rate is not None:
                would_apply = fx_response.data.get("would_apply", "N/A")
                fx_line = f"FX: {snapshot.effective_rate:.4f} (would_apply={would_apply})"

        text = (
            f"🗓 Daily digest {now_local.date().isoformat()}\n"
            "KPI today vs yesterday: N/A\n"
            "KPI 7d: N/A\n"
            f"{fx_line}\n"
            "Top problems: N/A"
        )
        sent = await self._safe_send(owner_id, text)
        if not sent:
            return
        notify_settings.digest_last_sent_at = now_utc
        await session.commit()
        await write_audit_event("notify_digest_sent", {"owner_id": owner_id, "date": now_local.date().isoformat()})

    async def _safe_send(self, chat_id: int, text: str, max_retries: int = 3) -> bool:
        loop = asyncio.get_running_loop()
        last_sent = self._chat_last_send_ts.get(chat_id)
        if last_sent is not None:
            wait = 1.0 - (loop.time() - last_sent)
            if wait > 0:
                await asyncio.sleep(wait)

        for attempt in range(max_retries):
            try:
                await self._bot.send_message(chat_id=chat_id, text=text, disable_notification=False)
                self._chat_last_send_ts[chat_id] = loop.time()
                return True
            except Exception as exc:
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is None and hasattr(exc, "message") and isinstance(exc.message, str):
                    parts = exc.message.split("retry after ")
                    if len(parts) > 1:
                        token = parts[-1].split()[0]
                        if token.isdigit():
                            retry_after = int(token)
                if retry_after is not None and attempt < max_retries - 1:
                    await asyncio.sleep(float(retry_after))
                    continue
                await write_audit_event("notify_error", {"stage": "send", "chat_id": chat_id, "message": str(exc)[:200]})
                return False
        return False

    async def _notify_error_with_cooldown(self, notify_settings, session, owner_id: int, message: str) -> None:
        now = datetime.now(timezone.utc)
        if notify_settings.last_error_notice_at and now - notify_settings.last_error_notice_at < timedelta(hours=1):
            return
        notify_settings.last_error_notice_at = now
        await session.commit()
        await write_audit_event("notify_error", {"owner_id": owner_id, "message": message[:200]})

    async def _acquire_lock(self) -> LockResult:
        redis = await get_redis()
        token = str(uuid.uuid4())
        acquired = await redis.set(self.LOCK_KEY, token, ex=self.LOCK_TTL_SECONDS, nx=True)
        return LockResult(acquired=bool(acquired), token=token)

    async def _release_lock(self, token: str) -> None:
        redis = await get_redis()
        try:
            current = await redis.get(self.LOCK_KEY)
            if current == token:
                await redis.delete(self.LOCK_KEY)
        except Exception:
            return

    async def stop(self) -> None:
        self._stopped = True
