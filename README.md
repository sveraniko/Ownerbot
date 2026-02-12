# OwnerBot (SIS Analytics & Control Layer)

OwnerBot — отдельный бот/сервис поверх SIS, который:
- читает события/метрики SIS (orders, payments, access, autonudge, content renew),
- даёт владельцу отчёты, прогнозы, алерты,
- управляет “верхними” настройками бизнеса (policy/config), не ломая SIS.

## What’s inside
- **AGENTS.md** — как работать с Codex/Qoder, роли, чек-листы, правила PR.
- **docs/** — база знаний и контракты:
  - PROJECT_BASE.md — контекст SIS и границы.
  - OWNER_BOT_BASE.md — что такое OwnerBot, архитектура, модули, роадмап.
  - OWNERBOT_TECH_BASE.md — техбаза OwnerBot (пакеты, инфраструктура, режимы).
  - OWNERBOT_TOOLS.md — контракты ToolRequest/ToolResponse и список tools v1.
  - SHARED_CONTRACTS.md — общие контракты данных/событий/идентификаторов.
  - UI_STATE_POLICY.md — правила UI/состояний (важно для SIS, чтобы не плодить ад).
  - ACCESS_MODEL.md — модель доступа (Gate + Levels + Content + Renew).

## Operating principles
- OwnerBot **не зависит** от релизов SIS и должен жить автономно.
- Любые интеграции с SIS — через **явные контракты** (docs/SHARED_CONTRACTS.md).
- Никаких “рефакторингов ради красоты” в боевом коде: только хирургия, только тестами.

## Workflow (PR discipline)
1. Прочитать **AGENTS.md** (обязательно).
2. Любая работа — через PR с названием вида:
   - `PR-OWNERBOT-XX: <short summary>`
3. Любые изменения контрактов:
   - сначала правим docs/**,
   - потом код,
   - потом тесты и проверка baseline/boot.

## Status
- Repo содержит автономный MVP OwnerBot (DEMO режим, tools-first каркас).

## Quick Start (Docker Compose)
1. Скопируй env файл:
   ```bash
   cp ENV.example .env
   ```
2. Укажи обязательные переменные:
   - `BOT_TOKEN` — Telegram bot token
   - `OWNER_IDS` — список owner user_id (через запятую)
   - `MANAGER_CHAT_IDS` — список chat_id для notify_team (через запятую)
3. Если у тебя уже была создана БД и ты подтянул PR-05E (baseline indexes), пересобери volume:
   ```bash
   docker compose down -v
   ```
4. Запусти:
   ```bash
   docker compose up --build
   ```
5. Добавь бота в нужные чаты/каналы/группы, иначе Telegram вернёт ошибку отправки.

## Local development
1. Create venv:
   ```bash
   python -m venv .venv
   ```
2. Activate:
   ```bash
   . .venv/bin/activate
   ```
   Windows PowerShell:
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
3. Install deps:
   ```bash
   pip install -r requirements.txt
   ```

## Running tests
- Local:
  ```bash
  pytest -q
  ```
- Docker:
  ```bash
  docker compose run --rm ownerbot_app pytest -q
  ```

## ENV vars (минимум)
- `BOT_TOKEN` — обязательный токен бота.
- `OWNER_IDS` — owner allowlist.
- `DATABASE_URL` — Postgres для OwnerBot.
- `REDIS_URL` — Redis для OwnerBot.
- `UPSTREAM_MODE` — `DEMO` (по умолчанию), `SIS_HTTP` (позже), `SIS_DB_RO` (позже).
- `ASR_PROVIDER` — `mock` (default) или `openai` для реального ASR.
- `OPENAI_API_KEY` — обязателен при `ASR_PROVIDER=openai`.
- `OPENAI_ASR_MODEL` — модель распознавания (по умолчанию `gpt-4o-mini-transcribe`).
- `OPENAI_LLM_MODEL` — модель планировщика интентов (например `gpt-4.1-mini`).
- `OPENAI_BASE_URL` — base URL OpenAI API (по умолчанию `https://api.openai.com`).
- `LLM_PROVIDER` — `OFF` (default), `OPENAI`, `MOCK`.
- `LLM_TIMEOUT_SECONDS` — таймаут вызова LLM planner.
- `LLM_MAX_INPUT_CHARS` — ограничение длины входного текста для planner.
- `LLM_ALLOWED_ACTION_TOOLS` — CSV allowlist action-tools для LLM (по умолчанию `notify_team,flag_order`).
- `ASR_TIMEOUT_SEC` — таймаут ASR запроса (сек).
- `ASR_MAX_RETRIES` — число ретраев для 429/5xx.
- `ASR_RETRY_BACKOFF_BASE_SEC` — базовый backoff (сек).
- `ASR_CONVERT_FORMAT` — формат конверсии `wav`/`webm` для voice.

## Security / Access gate
- `OWNER_IDS` — единственный allowlist для доступа к OwnerBot.
- Все non-owner updates (message/callback) блокируются middleware `OwnerGate`.
- По умолчанию deny остаётся тихим (без ответа пользователю), но попытки пишутся в audit event `access_denied`.
- Audit deny throttled по ключу `deny:{update_kind}:{user_id}` с TTL `ACCESS_DENY_AUDIT_TTL_SEC` (по умолчанию 60 сек), чтобы не спамить таблицу.
- `ACCESS_DENY_AUDIT_ENABLED` — включает/выключает запись deny-аудита (default: `true`).
- `ACCESS_DENY_NOTIFY_ONCE` — опциональный one-shot ответ `Нет доступа.` только в private chat и не чаще одного раза за TTL (default: `false`).

## DEMO mode
- По умолчанию `UPSTREAM_MODE=DEMO`.
- OwnerBot использует локальные demo таблицы, seeds при старте.
- Если настроить `UPSTREAM_MODE` на SIS-режим — при недоступности upstream вернётся ошибка `UPSTREAM_UNAVAILABLE`.

## Quick links
- Entry point: **AGENTS.md**
- OwnerBot scope: **docs/OWNER_BOT_BASE.md**
- Tech base: **docs/OWNERBOT_TECH_BASE.md**
- Tools contract: **docs/OWNERBOT_TOOLS.md**
- Shared contracts: **docs/SHARED_CONTRACTS.md**


## Artifacts (PR-06)
- PNG chart preset for revenue trend: `/trend [N]` (default `14`) and phrases like `график выручки 7 дней`.
- Weekly DEMO PDF preset: `/weekly_pdf` (aggregates `revenue_trend`, `kpi_snapshot`, `orders_search status=stuck`, `chats_unanswered`).
- Artifacts are sent directly in Telegram as photo/document while textual tool summary is preserved.
