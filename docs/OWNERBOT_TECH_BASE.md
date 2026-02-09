# OWNERBOT_TECH_BASE.md
> Техническая база OwnerBot. Этот документ описывает архитектуру пакетов, инфраструктурную независимость и режимы интеграции.

---

## 1) Архитектура пакетов (SSOT)
- **app/core** — настройки, логирование, DB/Redis, time/security.
- **app/bot** — Telegram entrypoint, routers, middlewares, keyboards.
- **app/tools** — contracts → registry → verifier → tool handlers.
- **app/asr** — voice pipeline (download → ASR provider → cache).
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

## 4) ACTION pipeline (dry_run → confirm → commit)
- Action tools запускаются только через подтверждение: первый вызов всегда `dry_run=True`.
- В ответе dry_run приходит preview + note “Требует подтверждения”.
- OwnerBot создаёт confirm token и показывает inline‑кнопки ✅/❌.
- При подтверждении выполняется commit с `dry_run=False`.
- Коммит защищён idempotency_key (uuid4), чтобы повторные подтверждения не дублировали действие.
- Некоторые action tools требуют bot context для реальной отправки сообщений; он прокидывается через routers.

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
