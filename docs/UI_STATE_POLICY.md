# UI_STATE_POLICY.md
> Политика управления UI‑сообщениями и состояниями (FSM/Redis) в SIS.  
> Цель: **предсказуемый UI**, отсутствие дублей/мусора, минимизация “магии”, и отсутствие “починили один переход, сломали три”.

---

## 0) TL;DR (инварианты)
- **FSM state — только для логики диалога**, не для долговременного хранения UI‑идентификаторов.
- **Якорные панели каталога** (Welcome / Catalog prompt) должны быть **SSOT‑управляемы**: отправили один раз → дальше только edit‑in‑place.
- **Эфемерные UI‑сообщения** удаляются при переходах (в пределах режима), но **не требуют архитектурного рефакторинга**.
- **Режимы UI**: `CATALOG`, `ADMIN_PANEL`, `WIZARD`, `SUPPORT`.  
  Переход между режимами = отдельная политика очистки.
- Нельзя разбрасывать `state.clear()` по проекту без сохранения контекста и without explicit policy.

---

## 1) Зачем вообще эта политика
Мы уже проходили:
- дубли панелей “Добро пожаловать/Каталог”,
- carrier‑сообщения ради перерисовки reply keyboard,
- потери message_id из‑за `state.clear()`,
- попытки “cleanup everywhere” (гарантированный ад).

Эта политика нужна, чтобы:
- Codex/Qoder не импровизировали,
- PR‑ы не ломали интерфейс случайно,
- логика была одинаковой для всех точек входа.

---

## 2) Термины
### 2.1 Anchor panel (якорь)
Сообщение, которое:
- существует постоянно (или пока не будет намеренно заменено),
- служит опорой UI, под ним всегда “лента”,
- не должно дублироваться.

Примеры:
- Welcome / legend panel (“Добро пожаловать”)
- Catalog prompt (“Каталог/Категории”)

### 2.2 Ephemeral message (эфемерка)
Сообщение, которое:
- показывается на короткое время,
- может быть удалено без потери UX,
- не является частью постоянного “каркаса”.

Примеры:
- “Товар добавлен в корзину”
- transient подтверждения
- временные подсказки

### 2.3 Mode switch
Переход между режимами интерфейса:
- CATALOG → ADMIN_PANEL
- ADMIN_PANEL → WIZARD
- WIZARD → CATALOG
- CATALOG ↔ SUPPORT

---

## 3) SSOT: где хранить message_id
### 3.1 Правило хранения
- **Anchor IDs** не храним в FSM как единственный источник, потому что:
  - `state.clear()` сносит всё,
  - FSM может мигрировать, очищаться, TTL.
- Anchor IDs должны быть:
  1) либо в Redis (как support паттерн),
  2) либо в устойчивом persisted store (таблица),
  3) либо в FSM, но при условии **никогда не делать state.clear()** (практически невыполнимо).

### 3.2 Рекомендуемый вариант
**Redis‑паттерн как в Support**, потому что он уже “выстрадан”:
- ключи `CATALOG_ANCHOR:*`
- TTL (например 180 дней)
- safe delete
- единая точка cleanup

---

## 4) Политика Reply keyboard vs Inline
### 4.1 Общий принцип
- Reply keyboard смена = риск и сложность (carrier, дубли, order changes).
- Inline keyboard edit‑in‑place стабильнее.

### 4.2 Политика по умолчанию
- **Каталог**: reply keyboard (4 кнопки home) остаётся **стабильной**.
- **Wizard header**: предпочитаем inline кнопки (Back/Cancel), чтобы не переключать reply keyboard.
- Любой новый wizard/flow **не имеет права** менять reply keyboard без явного решения.

---

## 5) Архитектура режимов UI
### 5.1 Режим CATALOG
- Всегда существует anchor:
  - `welcome/legend`
  - `category_prompt`
- При входе в каталог:
  - если anchor отсутствует → send и сохранить id
  - если anchor есть → edit message text / edit markup (in place)
- Дубли не допускаются.

### 5.2 Режим ADMIN_PANEL
- Admin panel UI может быть ephemeral или semi‑persistent, но:
  - вход в admin должен сохранять “catalog anchors”
  - выход в catalog должен возвращать стабильный anchor‑layout

### 5.3 Режим WIZARD
- Wizard header предпочтительно inline.
- Wizard cleanup:
  - удаляет wizard header + шаговые сообщения (если tracked)
  - не трогает catalog anchors (если выход в каталог)

### 5.4 Режим SUPPORT
- Уже реализован паттерн:
  - диалоговая “range” в Redis
  - cleanup range при выходе в каталог

---

## 6) Политика cleanup (что и где удаляем)
### 6.1 “Не делаем”
- не делаем “cleanup everywhere”
- не внедряем массово `state.clear()` без сохранения контекста
- не пытаемся удержать UI order “сверху/снизу” через invisible message hacks

### 6.2 “Делаем”
Есть **две стратегии**:

**A) Selective cleanup**
- Удаляем только известные ephemeral messages, ID которых мы сохранили.
- Плюсы: минимальный риск.
- Минусы: нужно tracking.

**B) Range cleanup (как support)**
- Храним first/last message_id диапазона и чистим range.
- Плюсы: чистит всё.
- Минусы: нужно аккуратно определять диапазон.

По умолчанию:
- Support: range cleanup
- Catalog anchors: no cleanup (SSOT edit)
- Wizards: selective cleanup

---

## 7) Переходы между режимами (контракт)
### 7.1 CATALOG → ADMIN_PANEL
- не удаляем anchors
- сохраняем ids (если в FSM) или просто “не трогаем” (если Redis)
- если есть ephemeral catalog overlays (например support prompt) — чистим

### 7.2 ADMIN_PANEL → WIZARD
- admin panel messages можно удалить/заменить
- reply keyboard **не меняем** (желательно)
- wizard header: inline

### 7.3 WIZARD → CATALOG
- удалить wizard header + wizard step messages
- показать catalog anchors (reuse/edit)
- никаких дублей

### 7.4 Любой переход с `state.clear()`
Если кто-то всё же делает `state.clear()`:
- обязан:
  - сохранить нужные anchor IDs (preserve)
  - или иметь redis‑SSOT и не зависеть от FSM

---

## 8) Где должен жить код для UI‑state
### 8.1 Единственный слой
- `app/bot/ui_state/*` (или аналогичный модуль) — SSOT, helper‑функции.
- Все места, которые рисуют/очищают anchors, должны дергать их.

Запрещено:
- копипастить “delete_message legend_id” в 10 местах.

### 8.2 Минимальный набор helpers
- `ensure_catalog_anchors(chat_id, user_id) -> ids`
- `render_catalog_home(chat_id, message_id, ...)`
- `cleanup_wizard_ui(chat_id, wizard_ids)`
- `cleanup_support_range(chat_id, user_id)`
- `preserve_ids_across_state_clear(keys=[...])`

---

## 9) Тестовая политика
Любой PR, который трогает UI‑state:
- должен добавить unit‑тест на отсутствие дублей anchors при:
  - повторном открытии каталога
  - вход/выход wizard
  - вход/выход admin
- должен проверять, что reply keyboard не пропадает в критических точках.

---

## 10) “Golden Rules” для агентов
- Если решение требует “перепахать 30 мест” → это неправильный уровень вмешательства.
- Если для решения нужно “cleanup everywhere” → это неправильный подход.
- Anchor panels = **SSOT**. Либо Redis, либо строго controlled.
- Reply keyboard switching = “опасная зона”. Делать только по особой необходимости.

---

## 11) PR‑шаблон для UI‑правок
В каждом PR, который трогает UI:
- Motivation: какая боль решается
- Invariants: что нельзя сломать
- Mode transitions affected: какие переходы
- Test plan: минимум 2 теста на anchors + 1 тест на reply keyboard (если затрагивается)
- Rollback: какие файлы откатить, если Telegram UI повёл себя иначе

---

## 12) Приложение: анти‑паттерны (не повторять)
- “Спрячем сообщение и удалим сразу” — Telegram не гарантирует.
- “Будем хранить anchor IDs в FSM и чистить state.clear()” — обязательно сломается.
- “Поставим invisible carrier message и будет порядок” — нет.
- “Переиспользуем message_id чужого сообщения” — ghost buttons и конфликт callback.

---

## 13) TODO (если захотим довести до идеала)
- Вынести catalog anchor IDs в Redis (по аналогии с support).
- Ввести `ui_session_id` для режима CATALOG и связать диапазоны ephemeral messages.
- Добавить “UI state registry” с TTL.

