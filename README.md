# OwnerBot (SIS Analytics & Control Layer)

OwnerBot — отдельный бот/сервис поверх SIS, который:
- читает события/метрики SIS (orders, payments, access, renew, sales health),
- даёт владельцу **быстрые отчёты** (включая графики/опц. PDF),
- умеет **делать действия** (Action Tools) безопасно: *preview → confirm → commit*,
- остаётся **автономным** (OwnerBot не должен падать, если SIS перезапустили/сломали).

> OwnerBot не “думает вместо владельца”. Он убирает рутину, не врёт и не делает коммиты без явного подтверждения.

---

## What’s inside

- **AGENTS.md** — как работать с Codex/Qoder, роли, чек-листы, правила PR.
- **docs/** — база знаний и контракты (обязательны к чтению перед изменениями):

### Start here (core)
- `docs/OWNER_BOT_BASE.md` — что такое OwnerBot, границы и роадмап.
- `docs/OWNERBOT_TECH_BASE.md` — техбаза (инфра, режимы, окружение).
- `docs/OWNERBOT_TOOLS.md` — контракт ToolRequest/ToolResponse + реестр tools.
- `docs/OWNERBOT_ACTIONS_MASTER.md` — **единая модель действий** (ACTION pipeline, idempotency, audit).
- `docs/OWNERBOT_TEMPLATES.md` — каталог **шаблонов** (кнопки/сценарии + voice mapping).
- `docs/OWNERBOT_ONBOARDING.md` — guided onboarding: status, presets, test run.

### SIS integration (contracts)
- `docs/OWNERBOT_SIS_ACTIONS_CONTRACT.md` — **канонический** контракт SIS Actions API (как *должно быть*).
- `docs/OWNERBOT_SIS_ACTIONS_CONTRACT_IMPLEMENTED_QODER.md` — контракт “как реализовано” (снято из кода SIS).
- `docs/SHARED_CONTRACTS.md` — общие идентификаторы/форматы (межсервисные контракты).
- `docs/PROJECT_BASE.md` — контекст SIS и границы.

### Ops / UI / audits
- `docs/UI_STATE_POLICY.md` — правила UI/состояний (важно, чтобы не плодить ад).
- `docs/ACCESS_MODEL.md` — модель доступа (Gate/Levels/Content/Renew).
- `docs/OWNERBOT_PROD_AUDIT.md` — прод-аудит/риски/жёсткие P0/P1 заметки.
- `docs/OWNERBOT_LLM_PROMPT.md` — structured system prompt / политика планировщика.
- `docs/SIS_MASTER_FX_OWNERBOT_PLAN.md` — мастер-план FX/репрайса и связки SIS↔OwnerBot.

---

## Operating principles (не ломать)

1) **OwnerBot автономен.** SIS может падать/пересобираться, OwnerBot живёт.
2) Любая интеграция с SIS — через **явные контракты** (docs/**).
3) Любые изменения контрактов:
   - сначала правим docs/**,
   - потом код,
   - потом тесты и проверка baseline/boot.
4) **Write-операции только через ACTION pipeline** (preview → confirm → commit)  
   см. `docs/OWNERBOT_ACTIONS_MASTER.md`.

---

## Status (текущее)

### Templates engine (catalog-as-data)
- Templates UI (`/templates`) is generated from catalog defs in `app/templates/defs/*.yml`.
- Generic templates router reads `TemplateSpec` and runs universal input-flow (Redis TTL state, parser-driven steps).
- Existing Prices / Products / Looks / Discounts templates are migrated to defs without changing ACTION pipeline semantics (`dry_run → confirm → commit`).
- Force-commit UX for anomalies and noop short-circuit remain unchanged.


- Standalone runtime: Docker Compose (Postgres + Redis + app).
- UPSTREAM режимы: DEMO / SIS_HTTP / AUTO (+ runtime toggle при включённом флаге).
- Presets/artifacts: графики (PNG) и weekly PDF (опционально).
- Action tools: безопасные действия через confirm + idempotency + audit.
- SIS gateway: read-only + actions API по контракту + shadow_check (DEMO vs SIS).

---

## Quick Start (Docker Compose)

1) Скопируй env:
```bash
cp ENV.example .env
```

2) Минимум:
- `BOT_TOKEN` — Telegram bot token
- `OWNER_IDS` — allowlist владельцев (CSV или JSON-массив, например `[1491225535, 7354501272]`)

Опционально для notify_team:
- `MANAGER_CHAT_IDS` — куда можно отправлять сообщения (CSV или JSON-массив)

3) Запуск:
```bash
docker compose up --build
```

4) Проверка:
- `/start` — короткий runtime статус (DB/Redis/режим, ASR/LLM) + показывает reply-меню
- `/menu` — главное меню OwnerBot (кнопки для Templates/Systems/Upstream/Tools/Help)
- `/templates` — основной UI шаблонов (также доступен через кнопку 📚 Шаблоны)
- `/systems` — полный диагностический обзор OwnerBot/SIS/(future SizeBot) + preflight summary
- `/shadow_check` — DEMO vs SIS сверка
- `/clean` — вручную очищает активную панель и transient-артефакты, оставляя home-якорь с reply keyboard

UI режим:
- Reply keyboard (📚 Шаблоны / ⚙️ Системы / 🔌 Upstream / 🧰 Tools / 🆘 Help) является постоянным home-якорем.
- Экранные ответы рендерятся в одном panel-сообщении (edit-in-place, fallback на replace).
- `/templates` работает через inline-навигацию в том же panel-сообщении; артефакты (png/pdf/doc) отправляются отдельно и очищаются при смене раздела best-effort.

> Preflight запускается до старта polling: при критически сломанном env и `PREFLIGHT_FAIL_FAST=1` процесс завершится сразу с логом `preflight_failed`.

> Формат list-переменных (`OWNER_IDS`, `MANAGER_CHAT_IDS`, `LLM_ALLOWED_ACTION_TOOLS`):
> - допустимы **CSV** (`a,b,c`) и **JSON-массив** (`["a", "b"]` / `[1,2]`);
> - пустое значение = пустой список;
> - inline-комментарии в значении запрещены (например `OWNER_IDS=1,2 # comment` приведёт к ошибке парсинга).

> Если ты менял baseline/migrations и уже есть “грязные” volume’ы:  
> `docker compose down -v` (осознанно, удалит данные OwnerBot).

---

## Local development

Требования: **Python 3.12 (предпочтительно)**, допустимо 3.11+.
Ключевые пины зависимостей: `aiogram==3.25.0`, `pydantic>=2.12,<2.13`, `pydantic-settings==2.12.0`.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Docker tests:
```bash
docker compose run --rm ownerbot_app pytest -q
```

---

## ENV vars (критичное)

### Owner access
- `OWNER_IDS` — единственный allowlist доступа к OwnerBot.

### OwnerBot storage
- `DATABASE_URL` — Postgres
- `REDIS_URL` — Redis

### Upstream (SIS)
- `UPSTREAM_MODE` — `DEMO` (default), `SIS_HTTP`, `AUTO`
- `SIS_BASE_URL` — base URL SIS
- `SIS_OWNERBOT_API_KEY` — ключ для SIS gateway (read-only и/или actions, в зависимости от конфигурации SIS)
- `SIS_TIMEOUT_SEC`, `SIS_MAX_RETRIES`, `SIS_RETRY_BACKOFF_BASE_SEC`

**Важно про Actions:**  
SIS Actions API использует заголовок **`X-OWNERBOT-KEY`** и правила allowlist’ов (shop/actor).  
См. `docs/OWNERBOT_SIS_ACTIONS_CONTRACT.md`.

### Runtime toggle (optional)
- `UPSTREAM_RUNTIME_TOGGLE_ENABLED`
- `UPSTREAM_REDIS_KEY`

### ASR / LLM (optional)
- `ASR_PROVIDER` (`mock`/`openai`), `OPENAI_API_KEY`, `OPENAI_ASR_MODEL`
- `LLM_PROVIDER` (`OFF`/`OPENAI`/`MOCK`), `OPENAI_LLM_MODEL`, `LLM_TIMEOUT_SECONDS`
- `LLM_ALLOWED_ACTION_TOOLS` — allowlist action-tools для планировщика (CSV или JSON-массив строк)

---

## Templates vs Voice

- **Templates** (кнопки/инпуты) закрывают “частые” задачи владельца: KPI, тренды, репрайс, bump, скидки, скрытие товаров, notify_team.
- **Voice** — для нестандартных/комбинированных запросов (но commit всё равно только через confirm).

Полный каталог: `docs/OWNERBOT_TEMPLATES.md`.

---

## Action tools (write) — как добавлять

Коротко:
1) Сперва обновляешь docs: `OWNERBOT_ACTIONS_MASTER.md` + `OWNERBOT_TEMPLATES.md` (если это шаблон).
2) Реализуешь tool: `dry_run()` и `commit()`.
3) Подключаешь в registry.
4) Тесты: tamper-block, idempotency, deterministic duplicates.
5) Audit + correlation_id обязателен.

Подробно: `docs/OWNERBOT_ACTIONS_MASTER.md`.

---

## Workflow (PR discipline)

1) Прочитать **AGENTS.md** (обязательно).
2) Любая работа — через PR:
   - `PR-OWNERBOT-XX: <short summary>`
3) Любые “косметические” рефакторы без причины запрещены.  
   Только изменения с пользой + тесты + docs.

---

## Quick links

- Entry point: **AGENTS.md**
- Action model: **docs/OWNERBOT_ACTIONS_MASTER.md**
- Templates: **docs/OWNERBOT_TEMPLATES.md**
- SIS Actions Contract (canonical): **docs/OWNERBOT_SIS_ACTIONS_CONTRACT.md**
- SIS Actions Contract (implemented): **docs/OWNERBOT_SIS_ACTIONS_CONTRACT_IMPLEMENTED_QODER.md**
- Tech base: **docs/OWNERBOT_TECH_BASE.md**
- Tools catalog: **docs/OWNERBOT_TOOLS.md**
- Prod audit: **docs/OWNERBOT_PROD_AUDIT.md**
