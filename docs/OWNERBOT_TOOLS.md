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
Если tool возвращает числовые KPI, `provenance.sources` **обязателен**, иначе `PROVENANCE_MISSING`.

## 3) Tools v1
### Реализовано (DEMO)
- `kpi_snapshot` — payload: `day?`; output: day, revenue_gross/net, orders_paid/created, aov.
- `orders_search` — payload: `status?`, `limit?`; output: count + orders list.
- `revenue_trend` — payload: `days`, `end_day?`; output: series + totals + delta_vs_prev_window.
- `order_detail` — payload: `order_id`; output: order fields (status, amount, customer, timestamps).
- `chats_unanswered` — payload: `limit?`; output: count + threads with last message timestamps.
- `flag_order` (action) — payload: `order_id`, `reason?`, `dry_run?`; output:
  - dry_run: preview (`dry_run`, `will_update`, `note`)
  - commit: `order_id`, `flagged`, `reason`

### Stub (NOT_IMPLEMENTED)
- `funnel_snapshot`
- `top_products`
- `inventory_status`
- `refunds_anomalies`
- `truststack_signals`
- `create_coupon` (action, поддерживает dry_run payload)
- `adjust_price` (action)
- `notify_team` (action)
- `pause_campaign` (action)
