# OWNERBOT UI Gap Analysis (proposal vs current code)

## Что уже есть в коде (и это важно не потерять)

1. **Inline UI уже частично реализован** через `/templates`: главное меню категорий + пагинация + запуск шаблонов + back-навигация. Это не «нет интерфейса», а скорее «нет owner-home панели».  
2. **Каталог инструментов большой и структурированный**: сейчас загружается **103 шаблона** из YAML (`reports/orders/team/systems/...`).  
3. **Голос/текст уже работают**: есть rule-based + LLM fallback в `owner_console`, плюс voice shortcuts в разделы templates.  
4. **Критичные action-флоу уже с безопасностью**: dry-run → confirm/force confirm через confirm tokens.

---

## Сопоставление `OWNERBOT_UI_PROPOSAL.md` с реальным состоянием

## 1) Главный экран
- **В proposal**: `/start` и `/menu` дают управленческую панель с 6 крупными разделами.
- **В коде**: `/start` только текстовый статус, **без inline-кнопок**; команды `/menu` нет.

**Вывод:** это главный gap №1 по discoverability.

## 2) Иерархия разделов
- **В proposal**: топ-уровень (Dashboard/Orders/Prices/Products/Notifications/Settings).
- **В коде**: есть категории templates, но они расширенные (`team`, `advanced`, `forecast`, `looks`, `discounts`) и показываются «как есть» из каталога.

**Вывод:** фактическая структура богаче proposal, но не оптимизирована под owner-first вход.

## 3) Быстрые slash-команды
- **В proposal**: `/kpi`, `/kpi7`, `/stuck`, `/fx`, `/digest`, `/health`.
- **В коде**: прямых handlers для этих команд нет; есть `/start`, `/help`, `/tools`, `/templates`, `/systems`, `/upstream`, `/sis_check`, `/flag`, `tpl_*`.

**Вывод:** proposal правильно закрывает UX-боль; сейчас есть функционал, но нет коротких «бизнес»-шорткатов.

## 4) Управление уведомлениями
- **В proposal**: удобные подменю digest/weekly/fx/escalation.
- **В коде**: инструменты `ntf_*` уже есть в templates-категории notifications (и их много), но нет сводной owner-панели статуса и one-click сценариев с понятным текстом.

**Вывод:** backend/инструменты готовы, UX-обёртка не доведена.

## 5) Upstream/system control
- **В proposal**: отдельная «настройки» с upstream и health.
- **В коде**: есть команды `/upstream*`, `/sis_check`, `/systems`, но они командо-центрические, не панельные.

**Вывод:** логика готова, нужен UI-слой orchestration.

---

## Что, вероятно, упущено в proposal (нюансы)

1. **Слой templates уже является рабочим SSOT для кнопочного UI**. Если строить новый интерфейс параллельно и дублировать callback протоколы — риск расхождения.
2. **Нужно сохранить mixed-mode (inline + natural language + voice)**: proposal это упоминает, но технически важно не «заблокировать» текстовый ввод в F.text цепочке.
3. **Router ordering критичен**: `templates` подключается раньше `owner_console`; любые новые catch-all handlers в новом UI должны быть аккуратны, иначе сломается state-input для template шагов.
4. **Action safety нельзя упростить**: dry-run/confirm/force уже встроены, новый UI должен переиспользовать текущий confirm flow, а не делать новый.
5. **Capability-aware visibility уже есть** (для SIS mode): новый Home UI должен учитывать это же правило, иначе появятся «кнопки-призраки».

---

## Рекомендация: реализация в 3 прагматичных этапа (без больших рисков)

## Этап A — Owner Home (минимальный риск, максимум ценности)
✅ **Статус: IMPLEMENTED (OB-UI-01).**
- Введён anchor-message подход: `/start`, `/menu`, `/templates` переиспользуют одно якорное сообщение.
- UI переведён в inline-first для home панели и переходов, без reply keyboard.

- Добавить `/menu` как alias к `/start`.
- На `/start` показывать **inline owner-home** (6 кнопок proposal) + блок статусов (DB/Redis/effective upstream/last digest).
- Кнопки верхнего уровня не исполняют tools напрямую, а открывают существующие template-категории/панели.

**Зачем бизнесу:** сокращает time-to-action владельца в первые 5 секунд.

## Этап B — Quick Actions (операционное ядро)
- Добавить slash алиасы:
  - `/kpi` → `RPT_KPI_TODAY`
  - `/kpi7` → `RPT_KPI_7D`
  - `/stuck` → `ORD_STUCK`
  - `/fx` → `PRC_FX_STATUS`
  - `/digest` → `NTF_SEND_DIGEST_NOW`
  - `/health` → `SYS_HEALTH`
- Реализацию делать через существующий `_run_template_action`/registry, без новых bypass-путей.

**Зачем бизнесу:** owner может управлять и кнопками, и muscle-memory командами.

## Этап C — Role-focused dashboards
- Собрать 3 curated экрана:
  1. **«Что горит»** (stuck + payment issues + unanswered + errors)
  2. **«Деньги сегодня»** (KPI + trend + FX)
  3. **«Риски склада»** (low stock + no photo/price + top movers)
- Не добавлять новую бизнес-логику: только orchestration существующих tools + форматирование.

**Зачем бизнесу:** меньше когнитивной нагрузки, быстрее управленческие решения.

---

## Бизнес-идеи сверх proposal (можно как backlog)

1. **Morning Brief auto-pin**: в 08:00 отправлять owner one-message бриф с 3 CTA-кнопками («Разобрать зависшие», «Проверить FX», «Напомнить команде»).
2. **Risk score карточка (0–100)**: агрегировать KPI drop + stuck + unanswered + errors в один owner-friendly индекс.
3. **One-tap delegation**: в каждом проблемном отчёте кнопка «Назначить менеджеру» (reuse `notify_team` + шаблоны причины).
4. **Decision journal (retrospective UX)**: после action фиксировать «что решили / почему» в 1-2 клика (опора на существующий retrospective storage).

---

## Приоритеты, если делать только одно

Если выбирать **одну** вещь сейчас: делайте **Этап A (Owner Home + /menu)**.  
Это даст максимальный UX-эффект без изменения доменной логики и с минимальным регрессионным риском.
