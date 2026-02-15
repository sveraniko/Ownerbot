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
    make_ops_event_key,
    normalize_digest_format,
    render_revenue_trend_png,
    render_weekly_pdf,
    should_send_digest,
    should_send_ops_alert,
    should_send_fx_apply_event,
    should_send_fx_delta,
    should_send_weekly,
    should_attempt_digest_quiet,
    should_force_heartbeat,
    quiet_digest_triggered,
    alert_triggered,
    build_ops_snapshot,
)
from app.tools.impl import kpi_compare, sis_fx_status


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
            ops_snapshot = None

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

            digest_include_ops = bool(getattr(notify_settings, "digest_include_ops", True))
            if notify_settings.ops_alerts_enabled or (notify_settings.digest_enabled and digest_include_ops):
                ops_snapshot = await build_ops_snapshot(
                    session,
                    correlation_id=f"notify-ops-{owner_id}",
                    rules=self._ops_rules_from_settings(notify_settings),
                )

            if notify_settings.ops_alerts_enabled and ops_snapshot is not None:
                await self._maybe_send_ops_alert(owner_id, notify_settings, session, ops_snapshot)

            if notify_settings.digest_enabled:
                await self._maybe_send_digest(owner_id, notify_settings, session, ops_snapshot=ops_snapshot, fx_status_response=fx_status_response)

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
    def _ops_rules_from_settings(notify_settings) -> dict[str, object]:
        return {
            "ops_unanswered_enabled": bool(getattr(notify_settings, "ops_unanswered_enabled", True)),
            "ops_unanswered_threshold_hours": int(getattr(notify_settings, "ops_unanswered_threshold_hours", 2)),
            "ops_unanswered_min_count": int(getattr(notify_settings, "ops_unanswered_min_count", 1)),
            "ops_stuck_orders_enabled": bool(getattr(notify_settings, "ops_stuck_orders_enabled", True)),
            "ops_stuck_orders_min_count": int(getattr(notify_settings, "ops_stuck_orders_min_count", 1)),
            "ops_stuck_orders_preset": str(getattr(notify_settings, "ops_stuck_orders_preset", "stuck")),
            "ops_payment_issues_enabled": bool(getattr(notify_settings, "ops_payment_issues_enabled", True)),
            "ops_payment_issues_min_count": int(getattr(notify_settings, "ops_payment_issues_min_count", 1)),
            "ops_payment_issues_preset": str(getattr(notify_settings, "ops_payment_issues_preset", "payment_issues")),
            "ops_errors_enabled": bool(getattr(notify_settings, "ops_errors_enabled", True)),
            "ops_errors_window_hours": int(getattr(notify_settings, "ops_errors_window_hours", 24)),
            "ops_errors_min_count": int(getattr(notify_settings, "ops_errors_min_count", 1)),
            "ops_out_of_stock_enabled": bool(getattr(notify_settings, "ops_out_of_stock_enabled", True)),
            "ops_out_of_stock_min_count": int(getattr(notify_settings, "ops_out_of_stock_min_count", 1)),
            "ops_low_stock_enabled": bool(getattr(notify_settings, "ops_low_stock_enabled", True)),
            "ops_low_stock_lte": int(getattr(notify_settings, "ops_low_stock_lte", 5)),
            "ops_low_stock_min_count": int(getattr(notify_settings, "ops_low_stock_min_count", 3)),
        }

    async def _maybe_send_ops_alert(self, owner_id: int, notify_settings, session, ops_snapshot: dict[str, object]) -> None:
        now = datetime.now(timezone.utc)
        rules = self._ops_rules_from_settings(notify_settings)
        warnings = list(ops_snapshot.get("warnings") or [])
        if warnings:
            await self._notify_ops_tool_warning_with_cooldown(notify_settings, owner_id, session, warnings)

        triggered, reasons = alert_triggered(ops_snapshot, rules)
        if not triggered:
            return

        event_key = make_ops_event_key(ops_snapshot, rules)
        if not should_send_ops_alert(
            now=now,
            last_sent_at=notify_settings.ops_alerts_last_sent_at,
            cooldown_hours=int(notify_settings.ops_alerts_cooldown_hours),
            last_seen_key=notify_settings.ops_alerts_last_seen_key,
            event_key=event_key,
        ):
            return

        message = self._format_ops_alert_message(ops_snapshot, str(notify_settings.digest_tz or "Europe/Berlin"), reasons)
        sent = await self._safe_send_message(owner_id, message)
        if not sent:
            return

        notify_settings.ops_alerts_last_seen_key = event_key
        notify_settings.ops_alerts_last_sent_at = now
        await session.commit()
        await write_audit_event(
            "notify_ops_alert_sent",
            {
                "owner_id": owner_id,
                "reasons": reasons,
                "counts": {
                    "unanswered_chats": int((ops_snapshot.get("unanswered_chats") or {}).get("count") or 0),
                    "stuck_orders": int((ops_snapshot.get("stuck_orders") or {}).get("count") or 0),
                    "payment_issues": int((ops_snapshot.get("payment_issues") or {}).get("count") or 0),
                    "errors": int((ops_snapshot.get("errors") or {}).get("count") or 0),
                    "out_of_stock": int((ops_snapshot.get("inventory") or {}).get("out_of_stock") or 0),
                    "low_stock": int((ops_snapshot.get("inventory") or {}).get("low_stock") or 0),
                },
                "correlation_id": f"notify-ops-{owner_id}",
            },
        )

    async def _notify_ops_tool_warning_with_cooldown(self, notify_settings, owner_id: int, session, warnings: list[str]) -> None:
        now = datetime.now(timezone.utc)
        last_notice = notify_settings.ops_alerts_last_error_notice_at
        if isinstance(last_notice, datetime) and last_notice.tzinfo is None:
            last_notice = last_notice.replace(tzinfo=timezone.utc)
        if last_notice and now - last_notice < timedelta(hours=12):
            return
        notify_settings.ops_alerts_last_error_notice_at = now
        await session.commit()
        await write_audit_event(
            "notify_ops_alert_tool_failed",
            {"owner_id": owner_id, "warnings": [str(w)[:180] for w in warnings[:5]]},
        )

    @staticmethod
    def _format_ops_alert_message(snapshot: dict[str, object], tz_name: str, reasons: list[str]) -> str:
        now = datetime.now(timezone.utc)
        try:
            now_text = now.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            now_text = now.isoformat()

        unanswered = snapshot.get("unanswered_chats") or {}
        stuck = snapshot.get("stuck_orders") or {}
        payment = snapshot.get("payment_issues") or {}
        errors = snapshot.get("errors") or {}
        inventory = snapshot.get("inventory") or {}

        lines = [
            f"🚨 Ops alerts (TZ {tz_name}, {now_text})",
            f"💬 Unanswered >{int(unanswered.get('threshold_hours') or 2)}h: {int(unanswered.get('count') or 0)}",
            f"🧾 Stuck orders: {int(stuck.get('count') or 0)}",
            f"💳 Payment issues: {int(payment.get('count') or 0)}",
            f"⚠️ Errors({int(errors.get('window_hours') or 24)}h): {int(errors.get('count') or 0)}",
            f"📦 Stock: out={int(inventory.get('out_of_stock') or 0)}, low={int(inventory.get('low_stock') or 0)}",
        ]
        top_lines: list[str] = []
        for thread in (unanswered.get("top") or [])[:1]:
            if isinstance(thread, dict):
                top_lines.append(f"• chat {thread.get('thread_id')}")
        for item in (stuck.get("top") or [])[:1]:
            if isinstance(item, dict):
                top_lines.append(f"• stuck {item.get('order_id')}")
        for item in (payment.get("top") or [])[:1]:
            if isinstance(item, dict):
                top_lines.append(f"• pay {item.get('order_id')}")
        if top_lines:
            lines.append("Top: " + " | ".join([str(x)[:50] for x in top_lines[:3]]))
        if reasons:
            lines.append("Reasons: " + ", ".join(reasons[:5]))
        return "\n".join(lines)

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

    async def _maybe_send_digest(self, owner_id: int, notify_settings, session, ops_snapshot: dict[str, object] | None = None, fx_status_response=None) -> None:
        now_utc = datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(str(notify_settings.digest_tz))
        except Exception:
            tz = ZoneInfo("Europe/Berlin")
        now_local = now_utc.astimezone(tz)
        last_sent_local = notify_settings.digest_last_sent_at.astimezone(tz) if notify_settings.digest_last_sent_at else None
        quiet_enabled = bool(getattr(notify_settings, "digest_quiet_enabled", False))
        quiet_reasons: list[str] = []

        if not quiet_enabled:
            if not should_send_digest(now_local=now_local, last_sent_at=last_sent_local, digest_time_local=notify_settings.digest_time_local):
                return
            if ops_snapshot is not None and ops_snapshot.get("warnings"):
                await self._notify_ops_tool_warning_with_cooldown(notify_settings, owner_id, session, list(ops_snapshot.get("warnings") or []))
        else:
            last_attempt_local = notify_settings.digest_last_attempt_at.astimezone(tz) if notify_settings.digest_last_attempt_at else None
            should_attempt = should_attempt_digest_quiet(
                now_local=now_local,
                last_sent_local=last_sent_local,
                last_attempt_local=last_attempt_local,
                digest_time_local=notify_settings.digest_time_local,
                attempt_interval_minutes=int(getattr(notify_settings, "digest_quiet_attempt_interval_minutes", 60) or 60),
            )
            if not should_attempt:
                return

            notify_settings.digest_last_attempt_at = now_utc
            await session.commit()

            precheck_kpi = {}
            try:
                kpi_res = await kpi_compare.handle(
                    kpi_compare.Payload(preset="wow"),
                    correlation_id=f"notify-digest-quiet-precheck-{owner_id}-kpi",
                    session=session,
                )
                if kpi_res.status == "ok":
                    delta = (kpi_res.data.get("delta") or {})
                    precheck_kpi = {
                        "revenue_net_wow_pct": (delta.get("revenue_net_sum") or {}).get("delta_pct"),
                        "orders_paid_wow_pct": (delta.get("orders_paid_sum") or {}).get("delta_pct"),
                    }
            except Exception as exc:
                await write_audit_event("notify_digest_precheck_failed", {"owner_id": owner_id, "stage": "kpi_compare", "message": str(exc)[:200]})

            digest_include_ops = bool(getattr(notify_settings, "digest_include_ops", True))
            digest_include_fx = bool(getattr(notify_settings, "digest_include_fx", True))
            if digest_include_ops and ops_snapshot is None:
                ops_snapshot = await build_ops_snapshot(
                    session,
                    correlation_id=f"notify-ops-digest-precheck-{owner_id}",
                    rules=self._ops_rules_from_settings(notify_settings),
                )
            if digest_include_fx and fx_status_response is None:
                fx_status_response = await sis_fx_status.handle(
                    sis_fx_status.Payload(),
                    correlation_id=f"notify-fx-digest-precheck-{owner_id}",
                    session=session,
                )

            fx_payload = fx_status_response.data if fx_status_response is not None and getattr(fx_status_response, "status", None) == "ok" else None
            quiet_triggered, quiet_reasons, quiet_debug = quiet_digest_triggered(
                kpi_summary=precheck_kpi,
                ops_snapshot=ops_snapshot if digest_include_ops else None,
                fx_status_payload=fx_payload if digest_include_fx else None,
                rules=self._ops_rules_from_settings(notify_settings)
                | {
                    "digest_quiet_min_revenue_drop_pct": float(getattr(notify_settings, "digest_quiet_min_revenue_drop_pct", 8.0)),
                    "digest_quiet_min_orders_drop_pct": float(getattr(notify_settings, "digest_quiet_min_orders_drop_pct", 10.0)),
                    "digest_quiet_send_on_ops": bool(getattr(notify_settings, "digest_quiet_send_on_ops", True)),
                    "digest_quiet_send_on_fx_failed": bool(getattr(notify_settings, "digest_quiet_send_on_fx_failed", True)),
                    "digest_quiet_send_on_errors": bool(getattr(notify_settings, "digest_quiet_send_on_errors", True)),
                },
            )
            heartbeat_forced = should_force_heartbeat(
                now_utc=now_utc,
                last_sent_at_utc=notify_settings.digest_last_sent_at,
                max_silence_days=int(getattr(notify_settings, "digest_quiet_max_silence_days", 7) or 7),
            )
            if not quiet_triggered and not heartbeat_forced:
                notify_settings.digest_last_skipped_at = now_utc
                await session.commit()
                await write_audit_event(
                    "notify_digest_skipped_quiet",
                    {
                        "owner_id": owner_id,
                        "date": now_local.date().isoformat(),
                        "reasons": [],
                        "debug": quiet_debug,
                    },
                )
                return

        bundle = await build_daily_digest(owner_id, session, correlation_id=f"notify-digest-{owner_id}", ops_snapshot=ops_snapshot)
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
        if quiet_enabled:
            await write_audit_event("notify_digest_sent_quiet_v1", {"owner_id": owner_id, "date": now_local.date().isoformat(), "format": digest_format, "reasons": quiet_reasons[:10]})
        else:
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
