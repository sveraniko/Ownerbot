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
- `kpi_snapshot`
- `orders_search`

### Stub (NOT_IMPLEMENTED)
- `revenue_trend`
- `funnel_snapshot`
- `order_detail`
- `chats_unanswered`
- `top_products`
- `inventory_status`
- `refunds_anomalies`
- `truststack_signals`
- `create_coupon` (action, поддерживает dry_run payload)
- `adjust_price` (action)
- `notify_team` (action)
- `pause_campaign` (action)
- `flag_order` (action)
