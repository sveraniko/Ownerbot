from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import BufferedInputFile

from app.core.audit import write_audit_event
from app.core.db import session_scope
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.notify import (
    NotificationSettingsService,
    build_daily_digest,
    build_weekly_digest,
    extract_fx_last_apply,
    extract_fx_rate_and_schedule,
    make_fx_apply_event_key,
    normalize_digest_format,
    render_revenue_trend_png,
    render_weekly_pdf,
    should_send_digest,
    should_send_fx_apply_event,
    should_send_fx_delta,
    should_send_weekly,
)
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
            fx_status_response = None

            needs_fx_status = any(
                (
                    notify_settings.fx_delta_enabled,
                    notify_settings.fx_apply_events_enabled,
                    notify_settings.digest_enabled and notify_settings.digest_include_fx,
                )
            )
            if needs_fx_status:
                fx_status_response = await sis_fx_status.handle(
                    sis_fx_status.Payload(),
                    correlation_id=f"notify-fx-{owner_id}",
                    session=session,
                )

            if notify_settings.fx_delta_enabled:
                await self._maybe_send_fx_delta(owner_id, notify_settings, session, fx_status_response)

            if notify_settings.fx_apply_events_enabled:
                await self._maybe_send_fx_apply_event(owner_id, notify_settings, session, fx_status_response)

            if notify_settings.digest_enabled:
                await self._maybe_send_digest(owner_id, notify_settings, session)

            if notify_settings.weekly_enabled:
                await self._maybe_send_weekly(owner_id, notify_settings, session)

    async def _maybe_send_fx_delta(self, owner_id: int, notify_settings, session, fx_status_response) -> None:
        now = datetime.now(timezone.utc)
        try:
            response = fx_status_response
            if response is None:
                response = await sis_fx_status.handle(sis_fx_status.Payload(), correlation_id=f"notify-fx-{owner_id}", session=session)
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
            sent = await self._safe_send_message(owner_id, message)
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

    async def _maybe_send_fx_apply_event(self, owner_id: int, notify_settings, session, fx_status_response) -> None:
        now = datetime.now(timezone.utc)
        try:
            response = fx_status_response
            if response is None:
                response = await sis_fx_status.handle(sis_fx_status.Payload(), correlation_id=f"notify-fx-{owner_id}", session=session)
            if response.status != "ok":
                await self._notify_error_with_cooldown(notify_settings, session, owner_id, "fx_apply_status_error")
                return

            last_apply, warning = extract_fx_last_apply(response.data)
            if last_apply is None:
                mode = str(get_settings().upstream_mode).upper()
                if mode != "DEMO" and warning in {"missing_last_apply", "last_apply_result_unsupported"}:
                    return
                await self._notify_fx_apply_parse_warning(notify_settings, owner_id, session, warning or "last_apply_parse_failed")
                return

            result = str(last_apply.get("result") or "")
            result_enabled = {
                "applied": bool(notify_settings.fx_apply_notify_applied),
                "noop": bool(notify_settings.fx_apply_notify_noop),
                "failed": bool(notify_settings.fx_apply_notify_failed),
            }.get(result, False)
            if not result_enabled:
                return

            event_key = make_fx_apply_event_key(last_apply)
            if not should_send_fx_apply_event(
                now=now,
                last_sent_at=notify_settings.fx_apply_last_sent_at,
                cooldown_hours=int(notify_settings.fx_apply_events_cooldown_hours),
                last_seen_key=notify_settings.fx_apply_last_seen_key,
                event_key=event_key,
            ):
                return

            message = self._format_fx_apply_message(last_apply, str(notify_settings.digest_tz or "Europe/Berlin"))
            sent = await self._safe_send_message(owner_id, message)
            if not sent:
                return

            notify_settings.fx_apply_last_seen_key = event_key
            notify_settings.fx_apply_last_sent_at = now
            await session.commit()
            await write_audit_event(
                "notify_fx_apply_event_sent",
                {
                    "owner_id": owner_id,
                    "result": result,
                    "affected_count": int(last_apply.get("affected_count") or 0),
                    "correlation_id": f"notify-fx-{owner_id}",
                },
            )
        except Exception as exc:
            await self._notify_error_with_cooldown(notify_settings, session, owner_id, f"fx_apply_event_failed:{str(exc)[:120]}")

    async def _notify_fx_apply_parse_warning(self, notify_settings, owner_id: int, session, warning: str) -> None:
        now = datetime.now(timezone.utc)
        if notify_settings.fx_apply_last_error_notice_at and now - notify_settings.fx_apply_last_error_notice_at < timedelta(hours=12):
            return
        notify_settings.fx_apply_last_error_notice_at = now
        await session.commit()
        await write_audit_event("notify_error", {"owner_id": owner_id, "message": f"fx_apply_parse:{warning}"[:200]})

    @staticmethod
    def _format_fx_apply_message(last_apply: dict[str, object], tz_name: str) -> str:
        result = str(last_apply.get("result") or "").upper()
        at = last_apply.get("at")
        at_text = "n/a"
        if isinstance(at, datetime):
            try:
                at_text = at.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S %Z")
            except Exception:
                at_text = at.isoformat()
        lines = [f"💱 FX apply: {result}", f"🕒 {at_text}"]
        if result == "APPLIED":
            lines.append(f"📦 affected: {int(last_apply.get('affected_count') or 0)}")
            if last_apply.get("rate"):
                lines.append(f"💲 rate: {last_apply.get('rate')}")
            if last_apply.get("delta_percent"):
                lines.append(f"📈 Δ%: {last_apply.get('delta_percent')}")
        elif result == "NOOP":
            reason = str(last_apply.get("reason") or "not_due")
            lines.append(f"ℹ️ reason: {reason}")
            if last_apply.get("rate"):
                lines.append(f"💲 rate: {last_apply.get('rate')}")
            if last_apply.get("delta_percent"):
                lines.append(f"📈 Δ%: {last_apply.get('delta_percent')}")
        else:
            error_text = str(last_apply.get("error") or "unknown_error")[:200]
            lines.append(f"❗ {error_text}")
        return "\n".join(lines)

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

        bundle = await build_daily_digest(owner_id, session, correlation_id=f"notify-digest-{owner_id}")
        digest_format = normalize_digest_format(notify_settings.digest_format)

        send_ok = await self._safe_send_message(owner_id, bundle.text)
        if not send_ok:
            return
        try:
            if digest_format == "png":
                png = render_revenue_trend_png(bundle.series, "Daily revenue trend", str(notify_settings.digest_tz))
                send_ok = await self._safe_send_photo(owner_id, png, "Daily digest chart")
            elif digest_format == "pdf":
                pdf = render_weekly_pdf(bundle)
                send_ok = await self._safe_send_document(owner_id, pdf, filename="daily_digest.pdf", caption="Daily digest PDF")
        except Exception as exc:
            await write_audit_event("notify_digest_render_failed", {"owner_id": owner_id, "format": digest_format, "message": str(exc)[:200]})
            return

        if not send_ok:
            return

        notify_settings.digest_last_sent_at = now_utc
        await session.commit()
        await write_audit_event("notify_digest_sent_v2", {"owner_id": owner_id, "date": now_local.date().isoformat(), "format": digest_format})

    async def _maybe_send_weekly(self, owner_id: int, notify_settings, session) -> None:
        now_utc = datetime.now(timezone.utc)
        try:
            weekly_tz = ZoneInfo(str(notify_settings.weekly_tz or notify_settings.digest_tz))
        except Exception:
            weekly_tz = ZoneInfo("Europe/Berlin")
        now_local = now_utc.astimezone(weekly_tz)
        last_local = notify_settings.weekly_last_sent_at.astimezone(weekly_tz) if notify_settings.weekly_last_sent_at else None
        if not should_send_weekly(
            now_local=now_local,
            last_sent_at_local=last_local,
            weekly_day_of_week=int(notify_settings.weekly_day_of_week),
            weekly_time_local=notify_settings.weekly_time_local,
        ):
            return

        bundle = await build_weekly_digest(owner_id, session, correlation_id=f"notify-weekly-{owner_id}")
        try:
            pdf = render_weekly_pdf(bundle)
        except Exception as exc:
            await write_audit_event("notify_weekly_render_failed", {"owner_id": owner_id, "message": str(exc)[:200]})
            return

        sent_doc = await self._safe_send_document(owner_id, pdf, filename="weekly_report.pdf", caption="📅 Weekly report")
        if not sent_doc:
            return
        sent_msg = await self._safe_send_message(owner_id, bundle.text)
        if not sent_msg:
            return

        notify_settings.weekly_last_sent_at = now_utc
        await session.commit()
        await write_audit_event("notify_weekly_sent", {"owner_id": owner_id, "week": str(now_local.isocalendar()[:2])[:200]})

    async def _safe_send_message(self, chat_id: int, text: str, max_retries: int = 3) -> bool:
        async def _sender():
            await self._bot.send_message(chat_id=chat_id, text=text, disable_notification=False)

        return await self._safe_send_with_retry(chat_id, _sender, max_retries=max_retries)

    async def _safe_send_document(self, chat_id: int, content: bytes, filename: str, caption: str, max_retries: int = 3) -> bool:
        async def _sender():
            await self._bot.send_document(chat_id=chat_id, document=BufferedInputFile(content, filename=filename), caption=caption)

        return await self._safe_send_with_retry(chat_id, _sender, max_retries=max_retries)

    async def _safe_send_photo(self, chat_id: int, content: bytes, caption: str, max_retries: int = 3) -> bool:
        async def _sender():
            await self._bot.send_photo(chat_id=chat_id, photo=BufferedInputFile(content, filename="digest.png"), caption=caption)

        return await self._safe_send_with_retry(chat_id, _sender, max_retries=max_retries)

    async def _safe_send_with_retry(self, chat_id: int, sender, max_retries: int = 3) -> bool:
        loop = asyncio.get_running_loop()
        last_sent = self._chat_last_send_ts.get(chat_id)
        if last_sent is not None:
            wait = 1.0 - (loop.time() - last_sent)
            if wait > 0:
                await asyncio.sleep(wait)

        for attempt in range(max_retries):
            try:
                await sender()
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
