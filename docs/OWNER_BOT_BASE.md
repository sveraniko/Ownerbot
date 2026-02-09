# OWNER_BOT_BASE.md
> Owner‑Bot — “директор по выручке” и “операционный мозг” поверх SIS.  
> Этот документ фиксирует: **что такое Owner‑Bot, что он должен уметь, как он интегрируется с SIS, и какие инварианты нельзя ломать**.

---

## 0) TL;DR
- Owner‑Bot = отдельный Telegram‑бот (или отдельный сервис), который читает аналитику/события SIS и помогает владельцу управлять выручкой.
- Он не “вместо админки”. Он **над админкой**: мониторинг, прогноз, алерты, рекомендации, авто‑рутина.
- Owner‑Bot должен жить **отдельно** (отдельные контейнеры/БД/Redis), чтобы пересборка магазина не валит мозг.
- Интеграция с SIS только по контракту: **events + read‑only queries** (или API), без прямого хаоса в БД без схемы.

---

## 1) Зачем Owner‑Bot (продуктовая цель)
### 1.1 Проблема реального бизнеса
- Покупка происходит спонтанно, часто ночью.
- Менеджер не 24/7.
- Просадки спроса усиливают цену ошибки: потерянный клиент = реальная дыра в выручке.
- В Telegram‑магазинах большинство “провалов” это:
  - недожатая оплата,
  - не обработанный заказ,
  - незакрытый “вопрос в поддержку”,
  - конфликт доступа/контента,
  - неправильные payment terms (deposit/preorder) или непонятный UX.

### 1.2 Что Owner‑Bot даёт владельцу
- “Пульт управления”: быстро понимать **что сейчас горит**.
- Автоматические алерты и сводки: без ручной проверки 20 чатов.
- Прогноз: “если так пойдёт, через неделю будет −X%”.
- Рекомендации: что сделать сегодня, чтобы вернуть выручку.

---

## 2) Границы системы (что Owner‑Bot НЕ делает)
- Не заменяет SIS (каталог, корзина, checkout).
- Не является админ‑панелью редактирования товаров (это в SIS).
- Не занимается полноценным CRM (может выдавать “рекомендуемые действия”, но не превращается в CRM‑монстра).
- Не делает “web‑тикеты”. Весь смысл SIS = Telegram‑ops.

---

## 3) Архитектура Owner‑Bot (как должно быть устроено)
### 3.1 Отдельность от SIS (обязательное)
Owner‑Bot должен запускаться автономно:
- отдельный Docker‑compose (или отдельный сервис в общем compose, но изолированно),
- **своя БД** (хотя бы для кэша/сессий/настроек/дедупа),
- **свой Redis** (если нужен),
- своя конфигурация, свои воркеры.

Причина: пересборка SIS или миграционный эксперимент не должен валить Owner‑Bot. Иначе это не “директор”, это пассажир.

### 3.2 Подходы к интеграции (порядок предпочтения)
1) **Event‑driven (рекомендовано)**  
   Owner‑Bot читает события SIS (analytics/event log) и строит витрины/метрики.
2) **Read‑only queries**  
   Owner‑Bot по расписанию читает агрегаты из SIS БД (только чтение).
3) **Сервис‑API (позже)**  
   SIS предоставляет минимальные эндпоинты/handlers. Owner‑Bot ходит туда.

Важно: прямое “Owner‑Bot лазит по всем таблицам SIS и делает как хочет” = ад и регрессии.

---

## 4) Источники данных (что Owner‑Bot потребляет)
### 4.1 Analytics events (SSOT для поведения)
Owner‑Bot строится вокруг “Event Catalog” SIS:
- order lifecycle: created/updated/paid/failed
- staged payments: stage change, due_now snapshot
- access: granted/denied/expired/renew
- autonudge: sent/failed/skipped, digest
- support: opened/question/replied (если есть)
- ops actions: taken/assigned/closed (если есть)

**Правило:** если в SIS нет события, Owner‑Bot слепой.  
Поэтому Owner‑Bot диктует требования к событиям, и это фиксируется контрактом.

### 4.2 Read models / витрины
Owner‑Bot держит у себя (или строит на лету):
- витрина “Orders needing attention”
- витрина “Payment funnel”
- витрина “Access/content issues”
- витрина “Support backlog”
- витрина “Top products/looks by conversion”

### 4.3 Raw таблицы SIS (только если нужно)
Чтение из:
- orders / payments
- access control (policies/grants/entitlements)
- business_events (если события там)
Но желательно через агрегаты и contract.

---

## 5) Функциональные модули Owner‑Bot
### 5.1 Daily/Hourly Digest (сводки)
- Утренний отчёт владельцу (09:00): вчера/последние 24 часа
- Дневной “midday check” (13:00)
- Вечерний отчёт (21:00)
- Быстрый “последние 2 часа” при включенном режиме

Содержимое:
- Выручка (gross/net), количество оплат, средний чек
- Сколько заказов на стадиях: pending/deposit_due/balance_due/preorder
- Сколько “застряли” > N часов
- Топ 5 товаров/луков по просмотрам→добавлениям→оплатам
- Ошибки: payment failed, access denied spikes, autonudge failures

### 5.2 Alerts (реальные тревоги, не спам)
Примеры:
- “Скачок unpaid orders”: +X% за 30 минут
- “Платёжный шлюз/инструкция сломалась”: рост failed
- “AutoNudge не отправляет”: digest_failed или sent=0 при наличии due
- “Access denied аномально растёт”: возможно неверная policy
- “Support backlog > N”: менеджер забил

### 5.3 Recommendations (что делать сейчас)
Owner‑Bot не должен быть мотивационным коучем. Он должен быть гадким, но полезным:
- “10 заказов deposit_due > 24h: нажми ‘пнуть’ / проверь инструкцию оплаты”
- “Слишком много denied CONTENT по курсу: вероятно истекли entitlements → предложить renew кампанию”
- “Товар X просмотры есть, покупок нет: проверь price / buy lock / UI карточки”

### 5.4 Control actions (минимальные, безопасные)
Действия владельца через Owner‑Bot должны быть ограничены:
- “Открыть список проблемных заказов” (с deep link в SIS админ чат/панель)
- “Включить/выключить AutoNudge” (через config/feature flag)
- “Изменить интервал digest” (owner-only)
- “Экспорт отчёта” (PDF/CSV) (опционально)

**Не давать Owner‑Bot права массово менять политики/оплаты** без явного режима.

---

## 6) UX Owner‑Bot (Telegram интерфейс)
### 6.1 Команды / intents
- `/status` — краткий статус: выручка, pending, alerts
- `/today` — срез за сегодня
- `/hot` — “горит прямо сейчас”
- `/funnel` — воронка оплат (staged)
- `/access` — доступы/истечения/renew
- `/nudge` — состояние autonudge и результаты
- `/top` — топ товаров/луков
- `/settings` — owner-only

### 6.2 Формат сообщений
- короткий headline (1–2 строки)
- блок “Проблемы”
- блок “Топ”
- блок “Рекомендации”
- inline кнопки: “Открыть в SIS”, “Детали”, “Экспорт”

### 6.3 Стиль
- кратко, жёстко, с фактами и цифрами.
- никаких “вдохновляющих речей”, только actionable.

---

## 7) Безопасность и роли
### 7.1 RBAC
- Owner‑Bot должен различать:
  - OWNER (единственный, полный доступ)
  - ADMIN/OPS (ограниченный доступ к просмотру/частичным командам)
- Критические настройки (policy/terms/autonudge) — owner-only.

### 7.2 Аудит действий
Любое действие через Owner‑Bot:
- логируется (who/when/what)
- эмитит событие в analytics (OWNERBOT_ACTION_*)

---

## 8) Инварианты интеграции (контрактные требования)
Owner‑Bot требует от SIS:
- стабильный event catalog (версии)
- наличие dedupe_key и timestamps
- идентификаторы business_id, user_id, order_id
- staged payment snapshot (due_now, remaining_due, stage)
- access decisions (deny_reason, expired_at, renew_supported) или события истечения

Иначе Owner‑Bot станет гаданием по внутренностям.

---

## 9) Набор метрик и KPI (что Owner‑Bot обязан считать)
### 9.1 Revenue KPIs
- Gross revenue (sum of paid)
- Net revenue (если есть комиссии)
- ARPU/avg order value
- Conversion: views→add_to_cart→checkout→paid

### 9.2 Payment staging KPIs
- count by stage (pending/deposit_due/balance_due/preorder)
- median time in stage
- % orders that drop after deposit (если депозит есть)
- due_now bucket distribution

### 9.3 Ops KPIs
- median time to take order in work
- backlog size
- SLA breaches (orders > N hours without action)

### 9.4 Access/Content KPIs
- denied spikes per target/action
- expired count
- renew conversion (if renew implemented)

---

## 10) Runtime и надёжность
### 10.1 Стабильность
- Owner‑Bot должен выживать, даже если SIS:
  - на перезапуске
  - на базовом тестировании
  - на частичном падении воркеров

### 10.2 Дедуп и анти-спам
- любые уведомления/алерты должны иметь dedupe window
- троттлинг по chat_id

---

## 11) План реализации (итерации)
### Stage 0 — Skeleton
- отдельный сервис/бот
- базовые команды `/status`, `/today`
- чтение событий SIS (read-only)

### Stage 1 — Core dashboards
- payment funnel (staged)
- orders needing attention
- access/content dashboard

### Stage 2 — Alerts + Recommendations
- детект аномалий
- рекомендации на основе правил
- owner-only actions (feature flags)

### Stage 3 — Forecasting
- простые прогнозы: moving average, сезонность (минимум)
- прогноз нагрузки ops и выручки

---

## 12) Что будет в следующем документе (контракт)
Следующий файл: `INTEGRATION_CONTRACT.md` (или `SHARED_CONTRACTS.md`):
- event list + schema
- обязательные поля
- версии
- dedupe contracts
- read-only query contracts (если нужны)

---

## 13) Контроль качества для агентов (Codex/Qoder)
- Любые изменения в SIS, влияющие на Owner‑Bot, должны:
  - добавлять события в analytics
  - обновлять event catalog
  - иметь тесты на schema/паритет
- Любые изменения Owner‑Bot не должны:
  - зависеть от внутренних деталей SIS без контракта
  - ломаться от baseline reset SIS

