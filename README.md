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
- Repo сейчас содержит документацию и правила разработки.
- Код появится после фикса контрактов интеграции и первичного skeleton.

## Quick links
- Entry point: **AGENTS.md**
- OwnerBot scope: **docs/OWNER_BOT_BASE.md**
- Shared contracts: **docs/SHARED_CONTRACTS.md**
