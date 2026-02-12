# OWNERBOT_TECH_BASE.md
> Техническая база OwnerBot. Этот документ описывает архитектуру пакетов, инфраструктурную независимость и режимы интеграции.

---

## 1) Архитектура пакетов (SSOT)
- **app/core** — настройки, логирование, DB/Redis, time/security.
- **app/bot** — Telegram entrypoint, routers, middlewares, keyboards.
- **app/tools** — contracts → registry → verifier → tool handlers.
- **app/asr** — voice pipeline (download → конвертация → ASR provider → cache).
- **app/actions** — dry_run → confirm → commit каркас + idempotency.
- **app/storage** — ORM модели + Alembic baseline.

## 2) Независимость от SIS
OwnerBot стартует автономно:
- собственные контейнеры **Postgres** и **Redis**;
- отдельный compose файл;
- собственная схема БД (baseline-first).

Пересборка/перезапуск SIS **не должен** валить OwnerBot.

## 3) Режимы интеграции
- **DEMO (default)** — локальные demo таблицы в OwnerBot DB.
- **SIS_HTTP (later)** — read-only HTTP/Tool gateway поверх SIS.
- **SIS_DB_RO (later)** — read-only доступ к SIS DB через контрактные read models.

Если SIS недоступен, OwnerBot возвращает структурированную ошибку `UPSTREAM_UNAVAILABLE`.

## 4) Voice / ASR
- `ASR_PROVIDER`: `mock` (default) или `openai`.
- Для `openai` используется endpoint `POST /v1/audio/transcriptions` (через `httpx`, без SDK).
- Telegram voice (ogg/opus) сначала конвертируется в `wav`/`webm` через `ffmpeg` (pipe I/O).
- Для конвертации требуется установленный `ffmpeg` в контейнере.

## 4) ACTION pipeline (dry_run → confirm → commit)
- Action tools запускаются только через подтверждение: первый вызов всегда `dry_run=True`.
- В ответе dry_run приходит preview + note “Требует подтверждения”.
- OwnerBot создаёт confirm token и показывает inline‑кнопки ✅/❌.
- При подтверждении выполняется commit с `dry_run=False`.
- Коммит выполняется по схеме `atomic claim (status=in_progress) → execute → finalize (committed/failed)`; claim фиксируется в БД до запуска tool handler.
- Коммит защищён idempotency_key (uuid4): дубли подтверждения до завершения получают `Уже выполняется. Подожди.`, после завершения — `Уже выполнено.`.
- Некоторые action tools требуют bot context для реальной отправки сообщений; он прокидывается через routers.
- Confirm token после подтверждения не удаляется мгновенно: ему ставится короткий TTL, чтобы повторный callback детерминированно отрабатывал через idempotency-статус.

## 5) Dev/Test workflow
### Локально
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### Docker
```bash
docker compose run --rm ownerbot_app pytest -q
```

## 6) Boundaries & Modules
- **Routers (`app/bot/routers/*`)**: только Telegram wiring (входящие update/callback, reply/edit, keyboard) и делегирование в сервисы.
- **Services (`app/bot/services/*`)**: прикладная логика роутинга интентов и запуска tools (`intent_router`, `tool_runner`).
- **UI (`app/bot/ui/*`)**: чистое форматирование текстов ответов без Telegram API вызовов.
- Правило: **No cross-router imports**. Роутеры не импортируют друг друга; общие функции выносятся в `services`/`ui`.

## 7) Contracts & Regression Tests
- Contract tests расположены в `tests/test_contract_*.py` и используют только stdlib (без `aiogram`/`sqlalchemy`).
- Фиксируются инварианты: callback prefixes (`confirm:`/`cancel:`), baseline-only migration policy (ровно один файл в `alembic/versions`), registry action/read contracts, router boundary `no cross-router imports`, обязательные ключи `ENV.example`.
- Эти тесты служат anti-regression слоем и должны запускаться в ограниченной среде без внешних зависимостей.

## 8) Security / Access gate
- `OwnerGateMiddleware` применён к message и callback update stream; доступ только для `OWNER_IDS`.
- Для non-owner deny по умолчанию silent (без ответа), но пишется audit событие `access_denied`.
- Audit deny throttled на уровне user + update-kind (`deny:{update_kind}:{user_id}`) с TTL из `ACCESS_DENY_AUDIT_TTL_SEC` (default 60s).
- Реализация throttle: Redis-first (`exists`/`setex`), fallback-safe in-memory LRU cache (process-local, max 1000 keys).
- Флаг `ACCESS_DENY_AUDIT_ENABLED` (default `true`) управляет записью deny-аудита.
- Флаг `ACCESS_DENY_NOTIFY_ONCE` (default `false`) включает опциональный ответ `Нет доступа.` только в private chat, также throttled по тому же TTL-ключу.

## 9) Database baseline
- OwnerBot придерживается baseline-only policy: в `app/storage/alembic/versions` хранится ровно одна миграция `0001_baseline.py`.
- Производственные индексы (audit/action/demo hot paths) добавляются только в baseline, без `0002+` ревизий.
- После pull изменений baseline (например, PR-05E) локальную БД нужно пересобрать через `docker compose down -v` перед `docker compose up --build`.
