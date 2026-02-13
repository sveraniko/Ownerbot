# SIS MASTER: FX / Валюты / Reprice / OwnerBot Actions

**Файл:** `docs/SIS_MASTER_FX_OWNERBOT_PLAN.md`  
**Статус:** Source-of-truth для задач по FX/валютам/репрайсу и интеграции с OwnerBot.  
**Кому читать:** Codex/Qoder/любой, кто полезет “чуть-чуть добавить кнопку”.

---

## 0) Цель документа

Сделать FX/валюты и действия управления магазином (цены/скрытие/скидки) **без усложнения UX магазина** и **без поломки** текущих расчётов (луки/корзина/скидки/минималка), при этом подготовить **чистый Action API** для OwnerBot (preview → confirm → commit).

---

## 1) Базовые принципы (не обсуждается)

### 1.1 UX магазина “Simple Insta Shop”
- В карточке товара/лука **не показывать** “База/Витрина”, курсы, формулы, валютные режимы.
- Пользователь видит **одну цену** и **одну валюту витрины**.
- Все “плюшки” прячем в админке в “Опции / Advanced”.

### 1.2 Runtime расчёты не трогаем
**Критично:** никаких конвертаций “на лету” в каталоге/корзине/луках.  
Все расчёты используют **одно поле цены** в **shop currency**.

> Вторая валюта (если включена) используется **только как параметр операции Reprice** (интерпретация текущих цен перед конвертацией). В runtime её не существует.

### 1.3 Репрайс = явная операция
- Есть **preview**, есть **apply**, есть **лог/аудит**.
- Репрайс может быть ручной и (опционально) по расписанию.
- В репрайсе учитываем:
  - курсы (snapshot),
  - наценку (percent + additive),
  - округление (только вверх).

### 1.4 Скидки при репрайсе НЕ пересчитываем
- Денежные скидки не конвертируем.
- При apply репрайса: **скидки отключаем/сбрасываем** для затронутых товаров/вариантов.
- Экономику скидок решает бизнес вручную.

### 1.5 Заказ фиксирует цены
- На момент заказа итоговая цена (после всех скидок/логики) должна быть записана в order items.
- `order.currency` = **shop currency**.
- `payment.currency` = **order.currency**.
- Никаких “UAH по умолчанию” в коде.

---

## 2) Термины

- **Shop currency** — валюта витрины/заказа/платежа (то, что видит клиент).
- **Price amount** — цена товара/варианта в базе (число) в shop currency.
- **FX provider** — источник курсов (Privat/Mono/ECB/NBP).
- **FX snapshot (rate set)** — сохранённый снимок курсов на момент времени.
- **Reprice input currency (опционально)** — “в какой валюте интерпретировать текущие price_amount перед конвертацией” (используется только в операции reprice).

---

## 3) Политика валют (минимум и “pro” режим)

### 3.1 По умолчанию (для 90% клиентов)
- Только **shop currency**.
- Цена товара = число в shop currency.
- FX используется только для “пересчитать цены”, если бизнес меняет валюту магазина.

### 3.2 Pro-режим (выключен по умолчанию)
Включается в “Опции → Advanced FX”:
- **Reprice input currency** (валюта ввода цен) может отличаться от shop currency.
- Это нужно для сценария: “цены в каталоге считаем как USD, пересчитываем в UAH/EUR”.

**Важно:** даже в pro-режиме после apply репрайса в базе остаётся одна цена в shop currency.

---

## 4) Админ UI (минимальные изменения)

### 4.1 Экран “Настройки → Валюта”
- Показать текущую shop currency (как сейчас).
- Кнопка **“Курс валют”** → wizard FX.

> UI валютных кнопок можно скрыть под “Валюта магазина” / “Валюта товара (advanced)” (dropdown/expand), чтобы не пугать.

### 4.2 Wizard “Курс валют” (FX)
Шаги:
1) Выбор провайдера (Privat/Mono/ECB/NBP)
2) Обновить snapshot (ручной fetch)
3) Показать:
   - provider
   - fetched_at
   - ключевые пары (EUR/UAH/USD/PLN)
4) Кнопка **“Пересчитать цены”** → wizard reprice.

### 4.3 Wizard “Пересчитать цены”
Параметры:
- rate snapshot (по умолчанию latest)
- markup:
  - `markup_percent`
  - `markup_additive` (в целевой валюте shop currency)
- rounding (только вверх):
  - `CEIL_INT`
  - `CEIL_0_50`
  - `CEIL_0_99`
  - (опц.) `CEIL_STEP`
- (Advanced) **reprice_input_currency** (если включён pro-режим)
- anomaly guard:
  - threshold_pct (например 25%)
  - require_confirm_on_anomaly

Flow:
- Preview:
  - affected_count
  - 5 примеров “было → стало”
  - warnings (аномалии)
- Apply:
  - применить новые price_amount
  - сбросить/выключить скидки у затронутых товаров/вариантов
  - записать job log + audit events

---

## 5) FX данные и хранение

### 5.1 Snapshot (rate set)
Рекомендовано отдельными таблицами (или эквивалент в ShopSettings, но таблицы лучше для аудита):

- `fx_rate_set`:
  - `id`
  - `provider`
  - `base_currency`
  - `fetched_at`
  - `raw_payload_hash`
- `fx_rate`:
  - `rate_set_id`
  - `quote_currency`
  - `rate_mid`

### 5.2 Reprice job log (обязательно)
- `fx_reprice_job`:
  - `id`
  - `from_currency` (input_currency)
  - `to_currency` (shop_currency)
  - `rate_set_id`
  - `markup_percent`
  - `markup_additive`
  - `rounding_mode`
  - `anomaly_threshold_pct`
  - `affected_count`
  - `started_at`, `finished_at`
  - `status` (previewed/committed/failed)
  - `error` (если failed)

### 5.3 Rollback (желательно)
Опционально:
- `fx_reprice_backup(job_id, product_id/variant_id, old_price_amount, old_discount_state_json)`
- Endpoint/действие “rollback last reprice”.

---

## 6) Удалить UAH literals (обязательное правило)

Запрещено:
- `currency = "UAH"` как дефолт/фолбек в бизнес-логике.

Инварианты:
- ShopSettings.pricing.currency_code — source-of-truth для shop currency.
- Order.currency выставляется явно при создании заказа.
- Payment.currency = Order.currency.
- OwnerBot gateway не возвращает константу “UAH”.

---

## 7) Anomaly guard (защита от “ночью продал в минус”)

### 7.1 Правило
Если при preview репрайса найдено изменение цены больше чем `threshold_pct`:
- показать WARNING блок + примеры
- потребовать явного подтверждения (confirm)
- отправить уведомление (notify_team / ownerbot)

### 7.2 Уведомления
Канал уведомления:
- либо существующая notify система SIS
- либо интеграция с OwnerBot notify_team action

Минимальный payload уведомления:
- provider
- fetched_at
- max_delta_pct
- affected_count
- top_examples

---

## 8) OwnerBot как Action Tool (цель интеграции)

OwnerBot не “вручную жмёт кнопки SIS”, а вызывает **Action API SIS**.

### 8.1 Набор Actions (минимум)
**Reprice**
- `POST /ownerbot/v1/actions/reprice/preview`
- `POST /ownerbot/v1/actions/reprice/apply`
- (опц.) `POST /ownerbot/v1/actions/reprice/rollback`

**Цены**
- `POST /ownerbot/v1/actions/prices/bump/preview`
- `POST /ownerbot/v1/actions/prices/bump/apply`
  - варианты: bump_all, bump_category, bump_filter

**Товары**
- `POST /ownerbot/v1/actions/products/hide_by_stock/preview`
- `POST /ownerbot/v1/actions/products/hide_by_stock/apply`
- (опц.) hide_by_age, hide_by_sales, etc.

**Скидки**
- `POST /ownerbot/v1/actions/discounts/apply_percent_by_stock/preview`
- `POST /ownerbot/v1/actions/discounts/apply_percent_by_stock/apply`

### 8.2 Контракт preview/apply
Preview возвращает:
- `affected_count`
- `examples: [{id, before, after}]` (до 5)
- `warnings: [...]`
- `summary`

Apply возвращает:
- `job_id` (если это job)
- `status`
- `summary`

### 8.3 Безопасность
- Allowlist (owner/admin) + shared secret API key.
- В OwnerBot: action pipeline (dry_run → confirm → commit) уже существует, его используем.
- SIS со своей стороны может быть “тонким” (проверка ключа + owner allowlist), чтобы не замедлять UX “ключевыми словами”.

---

## 9) OwnerBot Templates (UI, без голоса)

Меню:
- **Цены**
  - “Поднять все цены на %”
  - “Поднять цены категории на %”
  - “FX репрайс (по snapshot)”
  - “Rollback last reprice” (если есть)
- **Товары**
  - “Скрыть товары с остатком < N”
  - “Снять с публикации категорию”
- **Скидки**
  - “Скидка X% на остатки < N”
  - “Выключить все скидки”

UI:
- кнопки → если нужен ввод числа → input → preview → ✅ → отчёт.

Голос:
- только для сложных комбинированных запросов после того, как templates покрывают базу.

---

## 10) Тестирование (минимальный набор)

### 10.1 FX unit tests
- provider parsing (без реального HTTP)
- snapshot storage
- rounding (ceil modes)
- markup percent + additive
- reprice preview/apply
- anomaly detection

### 10.2 Business invariants
- no “UAH hardcode” в currency pipeline (кроме UI-лейблов)
- order.currency = shop currency
- payment.currency = order.currency

### 10.3 Action API tests
- preview idempotent / apply idempotent
- permission checks
- correlation_id / audit logs

---

## 11) Правила для Codex/Qoder (директива)

### 11.1 Перед любой работой
1) Прочитать этот документ полностью.
2) Найти существующие паттерны UI “панели/очистки” и **не ломать** их.
3) Не делать “рефакторинг ради кнопки”.

### 11.2 Что запрещено
- Переписывать роутеры/очистку UI “потому что так красивее”.
- Добавлять runtime конвертацию цен.
- Пересчитывать скидки как деньги.
- Вводить второй “прайс” в карточке товара.

### 11.3 Что обязательно
- Preview/Apply для любых денежных действий.
- Audit events + job log.
- Удаление UAH literals.

---

## 12) План PR-стека (следующий этап)

### SIS-FX-A1
Reprice input currency (advanced) + settings (default off).

### SIS-FX-A2
Anomaly guard + уведомления.

### SIS-FX-A3 (опционально, но желательно)
Rollback last reprice (backup storage).

### SIS-ACT-01
OwnerBot Action API: reprice + bump_all (preview/apply).

### OwnerBot-TPL-01
Templates: цены/товары/скидки на базе SIS Action API.

### OwnerBot-VOICE-01
Voice routing → templates/tools (после покрытия шаблонами).

---

## 13) Приложение: минимальные payload примеры

### Reprice preview request
```json
{
  "rate_set_id": 123,
  "input_currency": "USD",
  "shop_currency": "UAH",
  "markup_percent": 3.0,
  "markup_additive": 50.0,
  "rounding_mode": "CEIL_INT",
  "anomaly_threshold_pct": 25
}


### Reprice preview response
{
  "affected_count": 42,
  "max_delta_pct": 31.2,
  "warnings": ["ANOMALY_DETECTED"],
  "examples": [
    {"id": "SKU-1", "before": 10.0, "after": 420.0},
    {"id": "SKU-2", "before": 15.0, "after": 630.0}
  ],
  "summary": "Preview OK; confirm required due to anomaly threshold"
}


### Apply response

{
  "job_id": "FX-REP-2026-02-13-001",
  "status": "committed",
  "summary": "Prices updated: 42 items; discounts disabled on affected items"
}


