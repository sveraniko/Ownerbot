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

## 4) Dev/Test workflow
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
