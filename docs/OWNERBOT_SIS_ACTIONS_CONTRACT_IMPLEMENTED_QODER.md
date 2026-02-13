# OwnerBot SIS Actions API — Implemented Contract

> **Source of truth**: `app/api/ownerbot_actions.py` (340 lines)
> **Extracted from commit**: `6ba6f0c` (2026-02-13)

---

## Overview

| Property | Value |
|----------|-------|
| **Base URL** | `/ownerbot/v1/actions` |
| **Version** | v1 |
| **Transport** | HTTP/JSON |
| **Auth** | Header `X-OWNERBOT-KEY` |
| **Router registration** | `app/server.py:79` |

---

## Authentication

### Header
```
X-OWNERBOT-KEY: <api-key>
```

### Validation Logic (lines 69-83)

```python
# Priority:
# 1. Check OWNERBOT_API_KEY (single key) — if set, must match exactly
# 2. Else check OWNERBOT_API_KEYS (list) — any match accepted
# Uses secrets.compare_digest (timing-safe comparison)
```

### Settings Variables

| Variable | Type | Description |
|----------|------|-------------|
| `OWNERBOT_API_KEY` | `str \| None` | Single API key (takes priority) |
| `OWNERBOT_API_KEYS` | `list[str]` | List of allowed keys (CSV in env) |
| `OWNERBOT_ALLOWED_SHOP_IDS` | `list[int]` | Allowed shop IDs (default: `[1]`) |
| `OWNERBOT_SERVICE_ALLOWLIST` | `list[int]` | Allowed service Telegram IDs |
| `ADMIN_IDS` | `list[int]` | Admin Telegram IDs (always allowed) |

**Source**: `app/settings.py:130-133, 258-261`

---

## Common Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-OWNERBOT-KEY` | **Yes** | API authentication key |
| `X-CORRELATION-ID` | No | Request tracing ID (echoed in response) |
| `Content-Type` | Yes | `application/json` |

---

## Common Error Model

All errors return JSON:

```json
{
  "detail": "<error message>"
}
```

### HTTP Status Codes

| Code | Condition | Detail Message |
|------|-----------|----------------|
| 401 | Missing API key | `"Missing API key"` |
| 403 | Invalid API key | `"Invalid API key"` |
| 403 | Shop not allowed | `"Shop is not allowed"` |
| 403 | Actor not allowed | `"Actor is not allowed"` |
| 409 | Anomaly confirm required | `"Нужно явное подтверждение: применить несмотря на аномалию"` |
| 409 | Rollback failed | `"Нет данных для отката"` or `"Не удалось выполнить откат"` |
| 422 | Unknown rate_set_id | `"Unknown rate_set_id"` |
| 422 | Currency mismatch | `"shop_currency mismatch"` |
| 422 | Rate missing | `"В снимке нет курса для {currency}"` |

---

## Endpoints

### 1. POST `/reprice/preview`

**Purpose**: Preview FX reprice without applying changes.

#### Request Schema

```json
{
  "shop_id": 1,                    // int, default=1
  "actor_tg_id": 123456789,        // int, REQUIRED
  "actor_name": "John",            // string|null, optional
  "rate_set_id": "abc123hash",     // string, REQUIRED — must match last_snapshot.raw_payload_hash
  "input_currency": "USD",         // string, REQUIRED — source currency code
  "shop_currency": "EUR",          // string, REQUIRED — must match shop pricing.currency_code
  "markup_percent": "5",           // decimal, default="0"
  "markup_additive": "0",          // decimal, default="0"
  "rounding_mode": "CEIL_INT",     // string, default="CEIL_INT"
  "anomaly_threshold_pct": "25"    // decimal, default="25"
}
```

#### Response Schema (Success)

```json
{
  "affected_count": 150,
  "max_delta_pct": 12.5,
  "warnings": ["force required for apply"],  // present if anomaly detected
  "examples": [
    {"id": "product:1", "before": 100.0, "after": 112.0, "delta_pct": 12.0},
    {"id": "variant:5", "before": 50.0, "after": 56.0, "delta_pct": 12.0}
  ],
  "summary": "Preview ready for 150 items",
  "anomaly": {
    "threshold_pct": 25.0,
    "max_delta_pct": 12.5,
    "over_threshold_count": 0,
    "examples_over_threshold": []
  },
  "correlation_id": "req-uuid-123"
}
```

#### Rounding Modes

| Mode | Description |
|------|-------------|
| `CEIL_INT` | Round up to nearest integer |
| `CEIL_0_50` | Round up to nearest 0.50 |
| `CEIL_0_99` | Round up to X.99 |
| `CEIL_STEP` | Round up to custom step |

**Source**: `app/fx/reprice.py:94-107`

---

### 2. POST `/reprice/apply`

**Purpose**: Apply FX reprice to all products and variants.

#### Request Schema

```json
{
  "shop_id": 1,
  "actor_tg_id": 123456789,
  "actor_name": "John",
  "rate_set_id": "abc123hash",
  "input_currency": "USD",
  "shop_currency": "EUR",
  "markup_percent": "5",
  "markup_additive": "0",
  "rounding_mode": "CEIL_INT",
  "anomaly_threshold_pct": "25",
  "force": false                   // bool, default=false — REQUIRED if anomaly detected
}
```

#### Response Schema (Success)

```json
{
  "status": "committed",
  "job_id": 42,
  "summary": "Prices updated: 150 items; discounts disabled on affected items",
  "rollback_available": true,
  "rollback_job_id": 42
}
```

#### Side Effects

1. Creates `FxRepriceJob` record with status `"finished"`
2. Creates `FxRepriceBackup` records for each affected entity
3. Updates `shop_settings.fx.last_reprice_at` and `last_reprice_params`
4. **Disables all coupons** on affected products (`coupon_is_active=false`, `coupon_code=null`, etc.)
5. **Clears `compare_at_price`** on affected variants
6. Logs event `OWNERBOT_ACTION_APPLY` with `action="reprice"`

**Source**: `app/fx/reprice.py:222-336`

---

### 3. POST `/prices/bump/preview`

**Purpose**: Preview percentage bump on all prices.

#### Request Schema

```json
{
  "shop_id": 1,
  "actor_tg_id": 123456789,
  "actor_name": "John",
  "bump_percent": "10",            // decimal, REQUIRED
  "bump_additive": "0",            // decimal, default="0"
  "rounding_mode": "CEIL_INT"      // string, default="CEIL_INT"
}
```

#### Response Schema (Success)

```json
{
  "affected_count": 200,
  "max_delta_pct": 10.0,
  "warnings": [],
  "examples": [
    {"id": "product:1", "before": 100.0, "after": 110.0},
    {"id": "variant:5", "before": 50.0, "after": 55.0}
  ],
  "summary": "Preview ready for 200 items"
}
```

---

### 4. POST `/prices/bump/apply`

**Purpose**: Apply percentage bump to all prices.

#### Request Schema

Same as `/prices/bump/preview`

#### Response Schema (Success)

```json
{
  "status": "committed",
  "action_id": "bump-200",
  "summary": "Prices bumped for 200 items"
}
```

#### Side Effects

1. Updates `base_price` on all products
2. Updates `price` on all variants (where not null)
3. **Does NOT create backup** (no rollback available)
4. Logs event `OWNERBOT_ACTION_APPLY` with `action="bump_all"`

**Source**: `app/api/ownerbot_actions.py:259-296`

---

### 5. POST `/reprice/rollback/preview`

**Purpose**: Preview rollback of last FX reprice.

#### Request Schema

```json
{
  "shop_id": 1,
  "actor_tg_id": 123456789,
  "actor_name": "John"
}
```

#### Response Schema (Success — rollback available)

```json
{
  "affected_count": 150,
  "max_delta_pct": 0,
  "warnings": [],
  "examples": [
    {"id": "job:42", "before": "USD", "after": "EUR"}
  ],
  "summary": "Rollback available for job 42"
}
```

#### Response Schema (No rollback data)

```json
{
  "affected_count": 0,
  "warnings": ["NO_ROLLBACK_DATA"],
  "examples": [],
  "summary": "No rollback data"
}
```

---

### 6. POST `/reprice/rollback/apply`

**Purpose**: Execute rollback of last FX reprice.

#### Request Schema

Same as `/reprice/rollback/preview`

#### Response Schema (Success)

```json
{
  "status": "committed",
  "job_id": 42,
  "summary": "Rollback committed"
}
```

#### Response Schema (Already rolled back)

```json
{
  "status": "already_rolled_back",
  "job_id": 42,
  "summary": "Rollback already_rolled_back"
}
```

#### Side Effects

1. Restores `base_price` and coupon state on products
2. Restores `price` and `compare_at_price` on variants
3. Updates `FxRepriceJob.rolled_back_at`, `rolled_back_by`, `rollback_status`
4. Logs event `FX_REPRICE_ROLLBACK`

**Source**: `app/fx/reprice.py:360-412`

---

## Observability

### Correlation ID

All endpoints accept `X-CORRELATION-ID` header. Value is echoed in response (where applicable) and logged.

### Logged Events

| Event Name | Action | Source |
|------------|--------|--------|
| `fx_reprice_previewed` | Preview | `app/fx/reprice.py:204` |
| `fx_reprice_started` | Apply start | `app/fx/reprice.py:245` |
| `fx_reprice_finished` | Apply success | `app/fx/reprice.py:321` |
| `fx_reprice_failed` | Apply error | `app/fx/reprice.py:335` |
| `OWNERBOT_ACTION_APPLY` | Apply (any action) | `app/api/ownerbot_actions.py:202,284,327` |
| `FX_REPRICE_ROLLBACK` | Rollback | `app/fx/reprice.py:406` |

---

## Notes

### Code Locations

| Component | Path |
|-----------|------|
| API Router | `app/api/ownerbot_actions.py` |
| Auth dependency | `app/api/ownerbot_actions.py:69-83` |
| Actor/shop validation | `app/api/ownerbot_actions.py:86-94` |
| FxRepriceService | `app/fx/reprice.py:153-412` |
| Request models | `app/api/ownerbot_actions.py:35-62` |
| Settings | `app/settings.py:130-133, 258-261` |
| Router registration | `app/server.py:23, 79` |
| DB models | `app/infrastructure/models/fx.py` |

### Database Tables

| Table | Purpose |
|-------|---------|
| `fx_reprice_job` | Job history, rollback state |
| `fx_reprice_backup` | Price/discount snapshots for rollback |

### Anomaly Guard

- Configured via `anomaly_threshold_pct` (default 25%)
- If any item exceeds threshold → `warnings: ["force required for apply"]`
- Apply without `force: true` → HTTP 409
- Setting `fx.anomaly_require_force_confirm` can disable this check

### Limitations

1. **Bump has no rollback** — `/prices/bump/apply` does not create backups
2. **Only last job rollback** — Cannot rollback arbitrary job, only most recent finished
3. **Actor validation** — Must be in `ADMIN_IDS` or `OWNERBOT_SERVICE_ALLOWLIST`

---

## Example cURL

### Reprice Preview

```bash
curl -X POST http://localhost:8000/ownerbot/v1/actions/reprice/preview \
  -H "X-OWNERBOT-KEY: your-api-key" \
  -H "X-CORRELATION-ID: req-001" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_tg_id": 123456789,
    "rate_set_id": "snapshot-hash-here",
    "input_currency": "USD",
    "shop_currency": "EUR",
    "markup_percent": "5",
    "rounding_mode": "CEIL_INT"
  }'
```

### Reprice Apply (with force)

```bash
curl -X POST http://localhost:8000/ownerbot/v1/actions/reprice/apply \
  -H "X-OWNERBOT-KEY: your-api-key" \
  -H "X-CORRELATION-ID: req-002" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_tg_id": 123456789,
    "rate_set_id": "snapshot-hash-here",
    "input_currency": "USD",
    "shop_currency": "EUR",
    "markup_percent": "5",
    "force": true
  }'
```

### Bump Preview

```bash
curl -X POST http://localhost:8000/ownerbot/v1/actions/prices/bump/preview \
  -H "X-OWNERBOT-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_tg_id": 123456789,
    "bump_percent": "10"
  }'
```

### Rollback Apply

```bash
curl -X POST http://localhost:8000/ownerbot/v1/actions/reprice/rollback/apply \
  -H "X-OWNERBOT-KEY: your-api-key" \
  -H "X-CORRELATION-ID: req-003" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_tg_id": 123456789
  }'
```

---

*Document generated from code analysis. Last updated: 2026-02-13*
