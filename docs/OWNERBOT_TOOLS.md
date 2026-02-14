# OWNERBOT_TOOLS.md
> Контракт tools v1: envelope, provenance, список инструментов.

---

## 1) ToolRequest (v1)
```json
{
  "tool": "<name>",
  "version": "1.0",
  "correlation_id": "uuid",
  "idempotency_key": "uuid-or-hash",
  "actor": {"owner_user_id": 123, "role": "owner"},
  "tenant": {"project":"OwnerBot","shop_id":"shop_001","currency":"EUR","timezone":"Europe/Berlin","locale":"ru-RU"},
  "payload": {}
}
```

## 2) ToolResponse (v1)
```json
{
  "status": "ok|error",
  "correlation_id": "...",
  "as_of": "ISO8601",
  "data": {},
  "warnings": [{"code":"...","message":"..."}],
  "provenance": {"sources":["..."],"window":{},"filters_hash":"..."},
  "error": {"code": "...", "message": "...", "details": {}} 
}
```

### 2.1 Provenance правило
Если tool возвращает числовые KPI, `provenance.sources` **обязателен**, а также обязателен `provenance.window` и `as_of`.
При нарушении verifier возвращает `PROVENANCE_MISSING` или `PROVENANCE_INCOMPLETE`.

## 3) Tools v1
### Реализовано (DEMO)
- `kpi_snapshot` — payload: `day?`; output: day, revenue_gross/net, orders_paid/created, aov.
- `orders_search` — payload: `q?`, `status?`, `preset? (stuck|late_ship|payment_issues)`, `flagged?`, `limit?`, `since_hours?`; output: `count`, `items`, `applied_filters`.
- `revenue_trend` — payload: `days`, `end_day?`; output: series + totals + delta_vs_prev_window.
- `order_detail` — payload: `order_id`; output: order fields (status, amount, customer, timestamps).
- `chats_unanswered` — payload: `limit?`; output: count + threads with last message timestamps.
- `flag_order` (action) — payload: `order_id`, `reason?`, `dry_run?`; output:
  - dry_run: preview (`dry_run`, `will_update`, `note`)
  - commit: `order_id`, `flagged`, `reason`
- `notify_team` (action) — payload: `message`, `dry_run?`, `silent?`; output:
  - dry_run: preview (`dry_run`, `recipients`, `message_preview`, `note`)
  - commit: `sent`, `failed`, `message` (+ warnings on partial delivery)
  - allowlist: отправка только в `MANAGER_CHAT_IDS` (ENV)

- `retrospective_last` — payload: `limit?` (default=5); output: последние audit события `retrospective` из `ownerbot_audit_events` (read-only).

- `sis_prices_bump` (action) — SIS `/prices/bump/preview|apply`, payload: `bump_percent`, `bump_additive?`, `rounding_mode?`, `dry_run`.
- `sis_fx_reprice` (action) — SIS `/reprice/preview|apply`, payload: `rate_set_id`, `input_currency`, `shop_currency`, `markup_percent?`, `markup_additive?`, `rounding_mode?`, `anomaly_threshold_pct?`, `force?`, `dry_run`.
- `sis_fx_rollback` (action) — SIS `/reprice/rollback/preview|apply`, payload: `dry_run`.
- `sis_fx_status` (read) — SIS `GET /fx/status`, payload: `{}`.
- `sis_fx_reprice_auto` (action) — SIS `/fx/preview|apply`, payload: `dry_run`, `force?`, `refresh_snapshot?`; apply path uses Idempotency-Key.
- `sis_fx_settings_update` (action) — SIS `GET /fx/status` + `PATCH /fx/settings`, payload: `dry_run`, `updates{...}` (whitelist keys only).
- `sis_products_publish` (action) — SIS `/products/publish/preview|apply`, payload: `product_ids?`, `status_from?`, `target_status`, `reason?`, `force?`, `dry_run`.
- `sis_looks_publish` (action) — SIS `/looks/publish/preview|apply`, payload: `look_ids?`, `is_active_from?`, `target_active`, `reason?`, `force?`, `dry_run`.
- `sis_discounts_clear` (action) — SIS `/discounts/clear/preview|apply`, payload: `product_ids?`, `only_active?`, `clear_compare_at?`, `reason?`, `force?`, `dry_run`.
- `sis_discounts_set` (action) — SIS `/discounts/set/preview|apply`, payload: `product_ids?`, `only_active?`, `stock_lte?`, `discount_percent(1..95)`, `reason?`, `force?`, `dry_run`.

### Stub (NOT_IMPLEMENTED)
- `funnel_snapshot`
- `top_products`
- `inventory_status`
- `refunds_anomalies`
- `truststack_signals`
- `create_coupon` (action, поддерживает dry_run payload)
- `adjust_price` (action)
- `pause_campaign` (action)


## 4) Artifact presets (DEMO, no LLM orchestration)
- `/trend [N]` -> executes `revenue_trend` and renders PNG chart artifact (`chart_png`) + regular text summary.
- Phrase intents: `график выручки N дней`, `покажи график продаж N дней` map to the same `revenue_trend` + PNG presentation.
- `/weekly_pdf` -> preset workflow over existing tools: `revenue_trend(days=7)`, `kpi_snapshot`, `orders_search(status=stuck,limit=10)`, `chats_unanswered(limit=10)` and renders text-only PDF artifact (`weekly_pdf`).
- Artifact generation writes audit event `artifact_generated` with `correlation_id`.
