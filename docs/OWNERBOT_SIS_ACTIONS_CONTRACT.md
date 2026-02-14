# OwnerBot ↔ SIS Actions API — Canonical Contract (v1)

**File:** `docs/OWNERBOT_SIS_ACTIONS_CONTRACT.md`  
**Scope:** *Write-capable* endpoints on **SIS** that OwnerBot calls for business actions (repricing, bumps, rollback).  
**Source of truth (implementation):** `docs/OWNERBOT_SIS_ACTIONS_CONTRACT_IMPLEMENTED.md` (extracted from SIS code).  
**Design principle:** OwnerBot is responsible for **dry_run → confirm → commit** safety and idempotency (see `docs/OWNERBOT_ACTIONS_MASTER.md`). SIS enforces domain validation and anomaly guards.

---

## 1) Versioning & stability

- Contract version: **v1**
- Base path: **`/ownerbot/v1/actions`**
- Backwards compatibility: v1 endpoints must remain stable; additive fields are allowed.
- Breaking changes require **new version path** (v2) or explicit feature flag.

---

## 2) Authentication & authorization

### 2.1 Required auth header (Actions only)

```
X-OWNERBOT-KEY: <api-key>
```

- SIS validates the key against:
  - `OWNERBOT_API_KEY` (single, priority) or
  - `OWNERBOT_API_KEYS` (CSV list)
- Comparison is timing-safe.

> Note: SIS read-only OwnerBot endpoints (e.g., `/ownerbot/v1/kpi/...`) may use a different header (often `X-API-Key`). This document is **Actions only**.

### 2.2 Tenant / shop allowlist

Actions are limited by:
- `OWNERBOT_ALLOWED_SHOP_IDS` (default typically `[1]`)

If `shop_id` is not allowed → **403**.

### 2.3 Actor allowlist

Write operations require `actor_tg_id` and are allowed if:
- `actor_tg_id` ∈ `ADMIN_IDS` **OR**
- `actor_tg_id` ∈ `OWNERBOT_SERVICE_ALLOWLIST`

Otherwise → **403**.

---

## 3) Common headers

| Header | Required | Notes |
|---|---:|---|
| `X-OWNERBOT-KEY` | ✅ | authentication |
| `X-CORRELATION-ID` | recommended | request tracing; echoed in responses where supported |
| `Content-Type: application/json` | ✅ | POST only |

**Correlation rule:** OwnerBot must generate a UUID correlation_id per action and pass it through to SIS.

---

## 3.1 Response envelope (new)

SIS actions may return envelope:

```json
{
  "ok": true,
  "status": 200,
  "correlation_id": "...",
  "request_hash": "...",
  "warnings": [],
  "data": {},
  "error": null
}
```

OwnerBot should support both envelope and legacy plain JSON body for backward compatibility.

## 4) Common request fields

### 4.1 `shop_id`
- type: `int`
- default: `1` (if omitted)

### 4.2 `actor_tg_id` (required)
- type: `int`
- required for all endpoints

### 4.3 `actor_name` (optional)
- type: `string | null`

### 4.4 Decimal fields
Many numeric business inputs are modeled as **decimal strings** for precision:
- `markup_percent`, `markup_additive`, `bump_percent`, `bump_additive`, `anomaly_threshold_pct`

OwnerBot must send them as strings (or numbers that serialize cleanly) according to SIS request models.

---

## 5) Common error model (v1)

All errors return:

```json
{ "detail": "<human-readable message>" }
```

### Status codes (canonical meaning)

| HTTP | Meaning |
|---:|---|
| 401 | Missing API key |
| 403 | Invalid key OR shop/actor not allowed |
| 409 | Explicit force required OR rollback cannot be executed |
| 422 | Validation error (unknown rate_set_id, currency mismatch, missing rates, etc.) |

> Future-compatible improvement (optional v1.1): add `"error_code"` and `"correlation_id"` to error responses. v1 must keep working without it.

---

## 6) Endpoints

### 6.1 FX Reprice — Preview

**POST** `/reprice/preview`

Previews FX repricing of products/variants without applying changes.

#### Required request fields
- `actor_tg_id`
- `rate_set_id` — must match `last_snapshot.raw_payload_hash`
- `input_currency` — currency of stored base prices
- `shop_currency` — currency of storefront prices (must match SIS shop pricing currency)

#### Optional fields
- `shop_id`
- `actor_name`
- `markup_percent` (default `"0"`)
- `markup_additive` (default `"0"`)
- `rounding_mode` (default `"CEIL_INT"`)
- `anomaly_threshold_pct` (default `"25"`)

#### Response (success, shape)
- `affected_count`
- `max_delta_pct`
- `warnings[]`
- `examples[]` (≤N)
- `summary`
- `anomaly{...}`
- `correlation_id` (if SIS echoes it)

---

### 6.2 FX Reprice — Apply

**POST** `/reprice/apply`

Applies FX repricing. May require explicit force confirmation.

#### Request adds
- `force: bool` (default `false`)

#### Anomaly guard
- If preview detects deltas above `anomaly_threshold_pct`, SIS MUST require `force=true` on apply.
- If `force=false` → **409** with a “need explicit confirmation” message.

#### Side effects (canonical)
- Write job record (job_id)
- Write per-entity backups (for rollback)
- Update shop fx “last reprice params”
- Disable coupons and clear compare-at price for affected entities (as implemented)

#### Response (success)
- `status: "committed"`
- `job_id`
- `summary`
- `rollback_available: bool`
- `rollback_job_id` (when available)

---

### 6.3 Prices Bump — Preview

**POST** `/prices/bump/preview`

Preview a percentage + additive bump.

#### Required
- `actor_tg_id`
- `bump_percent`

#### Optional
- `bump_additive` (default `"0"`)
- `rounding_mode` (default `"CEIL_INT"`)

#### Response (success)
- `affected_count`
- `max_delta_pct`
- `warnings[]`
- `examples[]`
- `summary`

---

### 6.4 Prices Bump — Apply

**POST** `/prices/bump/apply`

Apply bump. **No rollback** is guaranteed in v1.

#### Side effects (canonical)
- Updates product base_price and/or variant price fields
- Logs event `OWNERBOT_ACTION_APPLY` with action `bump_all` (as implemented)

#### Response (success)
- `status: "committed"`
- `action_id`
- `summary`

---

### 6.5 FX Reprice Rollback — Preview

**POST** `/reprice/rollback/preview`

Preview rollback of the **most recent finished** reprice job.

#### Required
- `actor_tg_id`

#### Response
- If rollback available: affected_count + job info in examples, summary
- If not: warnings include `NO_ROLLBACK_DATA`, affected_count=0

---

### 6.6 FX Reprice Rollback — Apply

**POST** `/reprice/rollback/apply`

Execute rollback for the most recent finished job (if possible).

#### Response (success)
- `status: "committed"`, `job_id`, `summary`

#### Response (idempotent case)
- `status: "already_rolled_back"`, `job_id`, `summary`

#### Failure
- If rollback cannot be performed → **409**

---

## 7) Rounding modes

SIS supports the following rounding modes (v1):

- `CEIL_INT` — ceil to integer
- `CEIL_0_50` — ceil to 0.50 steps
- `CEIL_0_99` — ceil to X.99
- `CEIL_STEP` — ceil to custom step (if supported by request model)

OwnerBot must treat rounding as a business-rule knob, not an AI decision.

---

## 8) Observability

### 8.1 Correlation ID
OwnerBot should pass `X-CORRELATION-ID` for all action calls.
- SIS should echo it in response when possible.
- SIS should log it for all actions.

### 8.2 Logged events
SIS emits events for preview/apply/rollback paths. OwnerBot should not depend on their names, only on HTTP response success.

---

## 9) Safety & idempotency boundaries

- **OwnerBot** guarantees “exactly-once” execution from Telegram UX via confirm tokens + idempotency claim.
- **SIS** may be non-idempotent for apply endpoints (unless explicitly documented). OwnerBot should avoid retries on apply unless it can determine safe state.

**Retry rule (OwnerBot):**
- safe to retry: preview endpoints, ping/health
- unsafe to retry: apply endpoints (unless SIS adds explicit idempotency key in future)

---

## 10) Future extensions (non-breaking)

Optional v1.1 upgrades:
- Add `error_code` + `correlation_id` to error JSON
- Add `idempotency_key` header for apply endpoints
- Add “rollback bump” via backups (if product wants it)

---

## 11) Appendix: “As Implemented” reference

See: `docs/OWNERBOT_SIS_ACTIONS_CONTRACT_IMPLEMENTED.md`


### 6.7 FX Status

**GET** `/fx/status`

Returns current FX pipeline status/snapshot.

---

### 6.8 FX Reprice Auto — Preview

**POST** `/fx/preview`

Preview auto-reprice by current FX settings.

#### Required
- `actor_tg_id`

#### Optional
- `force_apply`
- `refresh_snapshot`

#### Envelope (v1.1 compatibility)
```json
{
  "ok": true,
  "status": 200,
  "correlation_id": "...",
  "request_hash": "...",
  "warnings": [],
  "data": {"would_apply": true, "status": "preview"},
  "error": null
}
```

No-op semantics: if `data.would_apply=false` OR `data.status in {"skipped","noop","no_change"}`, OwnerBot MUST NOT show confirm and MUST NOT call apply.

---

### 6.9 FX Reprice Auto — Apply

**POST** `/fx/apply`

Apply auto-reprice by current FX settings.

#### Required headers
- `Idempotency-Key: <ownerbot-idempotency-key>`

Apply must be idempotent end-to-end by this key.

---

### 6.10 FX Settings Update

**PATCH** `/fx/settings`

Update FX schedule/threshold/provider settings.

#### Required
- `actor_tg_id`
- `updates` object

#### Supported keys (B3)
- `reprice_schedule_mode`
- `reprice_schedule_interval_hours`
- `reprice_schedule_notify_on_success`
- `reprice_schedule_notify_on_failure`
- `min_rate_delta_abs`
- `min_rate_delta_percent`
- `min_apply_cooldown_hours`
- `provider`
