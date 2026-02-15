# OWNERBOT_NOTIFICATIONS.md

## Что это
OwnerBot notifications — owner-only подсистема уведомлений (только `OWNER_IDS`):
- FX delta сигнал (по порогу % и кулдауну в часах).
- Daily digest (один раз в день, в заданной timezone/time).

## Anti-spam
- FX уведомления отправляются только если изменение `>= threshold` и прошёл cooldown.
- Digest отправляется не чаще 1 раза в календарный день (локально в `digest_tz`).
- Ошибки апстрима/доставки имеют cooldown, чтобы не фладить каждую tick-итерацию.

## Worker
- Фоновый worker: `NotifyWorker`.
- Период: каждые 5 минут.
- Multi-instance safety: Redis distributed lock `ownerbot:notify:lock` (NX + EX).
- В DEMO режиме (`UPSTREAM_MODE=DEMO`) работает на demo FX payload.

## Как включить
1. Открой `/templates` → `🔔 Уведомления`.
2. Нажми `NTF статус` для проверки.
3. Включи `FX delta ON` и/или `Digest ON`.

## ENV
- `NOTIFY_WORKER_ENABLED=1` — включает worker на startup (по умолчанию включён).


## Digest v2 / Weekly
- Daily digest v2 uses real KPI + ops + FX summaries and supports `digest_format=text|png|pdf`.
- Weekly digest supports per-owner schedule (`weekly_enabled`, `weekly_day_of_week`, `weekly_time_local`, `weekly_tz`) and sends PDF.
- Safety: state (`digest_last_sent_at` / `weekly_last_sent_at`) updates only after successful send.


## FX apply events
- Новые event-уведомления о результате последнего `fx/apply`: `applied`, `noop`, `failed`.
- По умолчанию выключены (`fx_apply_events_enabled=false`), а из типов по умолчанию включён только `failed`.
- Дедупликация по ключу события + кулдаун (`fx_apply_events_cooldown_hours`, 1..168).
- При ошибке парсинга `last_apply` уведомление об ошибке троттлится (не чаще 1 раза в 12ч).
- При `UPSTREAM_MODE != DEMO` и отсутствии `last_apply` в `/fx/status` воркер тихо пропускает FX apply события (без спама).


## Ops alerts
- Owner-only operational alerts: unanswered chats, stuck orders, payment issues, recent errors, inventory risk.
- Disabled by default (`ops_alerts_enabled=false`).
- Alert is sent only when thresholds are triggered and both dedupe key + cooldown allow sending (`ops_alerts_cooldown_hours`, default 6h).
- Tool failures are throttled (`ops_alerts_last_error_notice_at`, 12h) and audited via `notify_ops_alert_tool_failed` without spamming Telegram.
- Safety: `ops_alerts_last_seen_key` / `ops_alerts_last_sent_at` are updated only after successful delivery.
