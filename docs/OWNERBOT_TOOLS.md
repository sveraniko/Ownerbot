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
- `notify_team` (action) — payload: `message`, `dry_run?`, `silent?`; output:
  - dry_run: preview (`dry_run`, `recipients`, `message_preview`, `note`)
  - commit: `sent`, `failed`, `message` (+ warnings on partial delivery)
  - allowlist: отправка только в `MANAGER_CHAT_IDS` (ENV)

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
