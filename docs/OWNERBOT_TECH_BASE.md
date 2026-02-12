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
