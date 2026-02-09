# SHARED_CONTRACTS.md
> Контракт интеграции SIS ↔ Owner‑Bot.  
> Цель: Owner‑Bot должен жить отдельно и стабильно, а SIS должен быть свободен эволюционировать, **не ломая надстройку**.  
> Этот документ определяет минимальные обязательства сторон: **события, схемы, идентификаторы, дедуп, версии, и read‑only витрины**.

---

## 0) TL;DR
- Главный канал интеграции: **Analytics Events** (SSOT).  
- Все события должны быть: versioned, idempotent/dedupe‑friendly, с едиными IDs (business_id/user_id/order_id/target).  
- Owner‑Bot не лазит “как хочет” по таблицам SIS. Если нужно чтение БД, оно оформляется как **Read Models** (контрактные запросы/витрины).
- Любые изменения в каталоге событий SIS = изменение контракта. Без этого Owner‑Bot слепнет и начинает “придумывать”.

---

## 1) Термины
- **Producer**: SIS (пишет события, хранит доменные данные)
- **Consumer**: Owner‑Bot (читает события/витрины, строит отчёты/алерты)
- **Event Catalog**: декларация событий и их схем (в SIS)
- **Dedupe key**: ключ идемпотентности события/уведомления
- **Target**: объект доступа (product/look/…)
- **Action**: VIEW / BUY / CONTENT
- **Stage**: стадия оплаты (staged payments)

---

## 2) Версионирование контракта
### 2.1 Contract version
- Файл версии контракта должен существовать в репо SIS и Owner‑Bot:
  - `CONTRACT_VERSION` (string) или `contract_version` в settings.
- Любой breaking change увеличивает major:
  - `1.x` → `2.0`

### 2.2 Event schema versioning
Каждое событие имеет:
- `event_name` (string, stable)
- `schema_version` (int, default 1)
- Добавление полей → minor update (schema_version++) или additive (если Consumer tolerates unknown)
- Удаление/переименование → breaking (major contract bump)

---

## 3) Каноническая модель события (Event Envelope)
> Важно: фактическая реализация в SIS может отличаться по колонкам, но логическая модель обязательна.

### 3.1 Required fields
- `event_id` (uuid/ulid/str) — уникальный ID события
- `event_name` (string)
- `occurred_at` (UTC timestamp)
- `business_id` (int/str)
- `schema_version` (int)
- `dedupe_key` (string, optional but strongly recommended)
- `context` (json, optional): request_id, chat_id, user_agent, etc.
- `properties` (json): payload

### 3.2 Subject fields (recommended)
События должны указывать “о ком/о чём”:
- `subject_type` (string): order/payment/access_policy/target_access/…
- `subject_id` (string/int)
- `actor_user_id` (int, optional): кто вызвал (админ/юзер)

### 3.3 Target fields (for access/content)
Когда событие связано с access decision:
- `target_type` (string): product/look/…
- `target_id` (int/str)
- `action` (string): view/buy/content

---

## 4) Dedupe / Idempotency contract
### 4.1 Dedupe key format (recommended)
- `dedupe_key = "{event_name}:{business_id}:{subject_type}:{subject_id}:{bucket}"`

Где `bucket`:
- для алертов: time bucket (например, “2026-02-06T20:00Z”)
- для lifecycle: stage name + order version

### 4.2 Consumer dedupe strategy
Owner‑Bot должен:
- хранить `dedupe_key → last_seen_at` с TTL
- не отправлять повторные уведомления в течение окна

### 4.3 Producer best practice
SIS должен:
- генерировать dedupe_key там, где важно не спамить (autonudge/digest/alerts)
- обеспечивать `occurred_at` и стабильный subject_id

---

## 5) Обязательные идентификаторы (ID contracts)
### 5.1 business_id
- Must exist в каждом событии и read model.

### 5.2 user_id
- Для user‑side действий:
  - `user_id` (telegram user id) в properties или actor_user_id.

### 5.3 order_id / payment_id
- Любые payment/order события должны содержать:
  - `order_id` (required)
  - `payment_id` (optional but recommended)

### 5.4 target composite
- `target_type + target_id` обязательны для access/content событий.

---

## 6) Event Catalog — группы событий (минимальный required set)
> Ниже “контрактный минимум”. SIS может иметь больше событий.

### 6.1 Orders lifecycle
- `ORDER_CREATED`
  - properties: order_id, user_id, total_amount, currency
- `ORDER_UPDATED` (optional)
  - properties: order_id, changes
- `ORDER_STATUS_CHANGED`
  - properties: order_id, old_status, new_status

### 6.2 Payments lifecycle (staged aware)
- `PAYMENT_REQUESTED`
  - properties: order_id, due_now, stage, payment_method
- `PAYMENT_CONFIRMED`
  - properties: order_id, payment_id, amount_paid, stage_after, paid_at
- `PAYMENT_FAILED`
  - properties: order_id, payment_id, reason

### 6.3 Staged payments snapshots (SSOT)
- `ORDER_DUE_SNAPSHOT`
  - properties:
    - order_id
    - payment_plan (full/deposit/preorder)
    - payment_stage
    - total_amount
    - amount_paid
    - upfront_due
    - due_now
    - remaining_due
    - computed_at

**Контрактное правило:** Owner‑Bot строит funnel/алерты по due_now/stage на основании snapshot событий, а не “угадывает”.

### 6.4 Access control decisions (LEVELS)
- `TARGET_ACCESS_GRANTED`
  - properties: target_type, target_id, action, mode (public/club/entitlement/key_offer/…)
- `TARGET_ACCESS_DENIED`
  - properties: target_type, target_id, action, reason_code, required_mode
- `TARGET_ACCESS_EXPIRED` (если эмитится отдельно)
  - properties: target_type, target_id, action, expired_at

### 6.5 Renew
- `ACCESS_RENEW_OFFERED`
  - properties: target_type, target_id, action, expired_at, renew_supported
- `ACCESS_RENEW_COMPLETED`
  - properties: target_type, target_id, action, new_expired_at, method

### 6.6 AutoNudge
- `AUTO_NUDGE_SENT`
  - properties: order_id, stage, due_now, channel (dm/ops), template
- `AUTO_NUDGE_FAILED`
  - properties: order_id, stage, reason
- `AUTO_NUDGE_SKIPPED`
  - properties: order_id, stage, reason
- `AUTO_NUDGE_DIGEST_SENT`
  - properties: interval_seconds, window_from, window_to, counts, top_orders
- `AUTO_NUDGE_DIGEST_FAILED`
  - properties: reason
- `AUTO_NUDGE_DIGEST_SKIPPED`
  - properties: reason

### 6.7 Support / Ops (если включено)
- `SUPPORT_THREAD_OPENED`
- `SUPPORT_MESSAGE_FORWARDED`
- `SUPPORT_REPLY_SENT`
- `OPS_ORDER_TAKEN`
- `OPS_ORDER_CLOSED`
(не строго required, но сильно помогает Owner‑Bot)

---

## 7) Схемы свойств (property schema contract)
### 7.1 Типы
- timestamp: ISO8601 UTC
- money: decimal as string OR integer minor units (фиксировать в контракте)
- enums: lower_snake_case strings

### 7.2 Money representation rule
Нужно выбрать один подход и держать:
1) **decimal string** (например "19.99") + `currency`  
или  
2) integer minor units (например 1999) + `currency`

Рекомендация для Telegram‑коммерции: **decimal as string** (чтобы не сломать отображение в UI и не страдать с minor units везде).

### 7.3 Enum normalization
- payment_plan: `full | deposit | preorder`
- payment_stage: `pending | deposit_due | balance_due | fully_paid | preorder`
- action: `view | buy | content`
- target_type: `product | look`

---

## 8) Read Models (контрактные витрины для Owner‑Bot)
> Это опционально, но часто удобно для быстрых отчётов.  
> Реализуется либо как SQL view/materialized view, либо как domain query service в SIS (read-only).

### 8.1 Orders needing attention
Contract: `RM_ORDERS_ATTENTION`
- filters: business_id, stage, older_than_minutes, limit
- result fields:
  - order_id, user_id
  - stage, due_now, remaining_due
  - created_at, updated_at
  - last_nudge_at (optional)
  - flags: has_content_items, has_expired_access (optional)

### 8.2 Payment funnel summary
Contract: `RM_FUNNEL_SUMMARY`
- fields:
  - window_from/window_to
  - counts by stage
  - revenue_paid
  - conversion metrics (if available)

### 8.3 Access issues summary
Contract: `RM_ACCESS_ISSUES`
- fields:
  - denied_count, expired_count
  - top targets by denies
  - top targets by expiries

### 8.4 Top products/looks
Contract: `RM_TOP_ITEMS`
- fields:
  - item_type (product/look)
  - item_id
  - views, adds_to_cart, checkouts, paid_count
  - revenue

---

## 9) Transport / Storage of events
### 9.1 Minimal implementation (acceptable)
- Owner‑Bot читает события напрямую из таблицы SIS (business_events/event_log) read-only.
- Требование: индекс по `(business_id, occurred_at)` и возможность paging.

### 9.2 Better implementation (later)
- SIS публикует события в очередь (Redis stream/Kafka/etc).
- Owner‑Bot потребляет и сохраняет локально.

---

## 10) Compatibility rules (Consumer must be tolerant)
Owner‑Bot обязан:
- игнорировать неизвестные события
- игнорировать неизвестные поля в properties
- требовать только минимальный required set
- если required поле отсутствует → логировать и продолжать, не падать

---

## 11) Change management (как не устроить ад)
### 11.1 Additive changes
- можно добавлять новые события
- можно добавлять поля в properties
- можно добавлять read models

### 11.2 Breaking changes
- переименование event_name
- удаление поля required
- изменение semantics enum
- изменение money representation

В этом случае:
- bump major contract version
- transitional period: SIS emits both old+new events (если нужно)

---

## 12) Checklist для PR в SIS, который влияет на Owner‑Bot
- [ ] Добавлены/обновлены события в event catalog
- [ ] Есть schema_version
- [ ] Есть dedupe_key (если событие может спамить)
- [ ] В properties есть business_id, order_id/target_id где нужно
- [ ] Baseline updated (если добавляли таблицы для дедуп/состояния)
- [ ] Unit tests: schema/паритет/минимальный smoke
- [ ] Документ CONTRACT_VERSION обновлён (если breaking)

---

## 13) Checklist для PR в Owner‑Bot
- [ ] Consumer tolerant к unknown events/fields
- [ ] Встроенный dedupe для уведомлений
- [ ] Не делает write в SIS
- [ ] Нормальные тайм‑окна и лимиты
- [ ] Логи ошибок без падения

---

## 14) Appendix: Suggested event names map (reference)
> Точные названия берём из SIS event_catalog.py. Этот список как ориентир, не “истина”.

- ORDER_CREATED
- ORDER_STATUS_CHANGED
- PAYMENT_REQUESTED
- PAYMENT_CONFIRMED
- PAYMENT_FAILED
- ORDER_DUE_SNAPSHOT
- TARGET_ACCESS_GRANTED
- TARGET_ACCESS_DENIED
- TARGET_ACCESS_EXPIRED
- ACCESS_RENEW_OFFERED
- ACCESS_RENEW_COMPLETED
- AUTO_NUDGE_SENT
- AUTO_NUDGE_FAILED
- AUTO_NUDGE_SKIPPED
- AUTO_NUDGE_DIGEST_SENT
- AUTO_NUDGE_DIGEST_FAILED
- AUTO_NUDGE_DIGEST_SKIPPED

