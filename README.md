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
3. Запусти:
   ```bash
   docker compose up --build
   ```

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
