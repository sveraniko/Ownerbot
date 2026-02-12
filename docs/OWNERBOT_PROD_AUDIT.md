# OwnerBot engineering audit (production hardening)

## Scope and method
- Reviewed runtime entrypoints, middleware chain, routers, tool registry, storage/baseline, and test suite.
- Checked module boundaries (`bot/*`, `tools/*`, `storage/*`, `core/*`) and coupling hotspots.
- Ran `python -m compileall -q app tests` and `pytest -q` in current environment.

## 1) Architecture map
- Entrypoint: `app/bot/main.py`
  - Wires middleware (`CorrelationMiddleware`, `OwnerGateMiddleware`) and routers (`start`, `owner_console`, `actions`).
  - Executes startup migrations + demo seed before polling.
- Config / ENV: `app/core/settings.py` (`BOT_TOKEN`, `OWNER_IDS`, `MANAGER_CHAT_IDS`, `DATABASE_URL`, `REDIS_URL`, ASR/openai envs).
- Tool registry: `app/tools/registry_setup.py` + `app/tools/registry.py`.
- Runtime handlers:
  - `app/bot/routers/start.py` — health/help/tools commands.
  - `app/bot/routers/owner_console.py` — intent parsing, text+voice entrypoint, tool execution, dry-run confirmation token creation.
  - `app/bot/routers/actions.py` — confirm/cancel callbacks + idempotency check + commit.
- Storage and baseline:
  - SQLAlchemy models: `app/storage/models.py`.
  - Baseline migration: `app/storage/alembic/versions/0001_baseline.py`.
  - Bootstrapping and audit writer: `app/storage/bootstrap.py`.

## 2) Risk register

### P0 (prod/data/access impact)
1. **Dry-run/action atomicity gap (double-commit race).** ✅ fixed in PR-05A
   - Fixed by switching to atomic `claim_action` (insert `in_progress` with unique idempotency key) before tool execution, followed by `finalize_action` terminal status update.
   - Duplicate confirms now resolve deterministically via existing row status (`in_progress` / `committed` / `failed`) without re-running handler.
   - Confirm token is expired with short TTL (instead of immediate delete) so duplicate callbacks still surface idempotent UX.
2. **Access gating is owner-only and silent for non-owner traffic.**
   - `OwnerGateMiddleware` drops unauthorized events with `return None`; no alerting/throttling/audit for repeated unauthorized attempts.
   - This is secure by deny-default but weak for diagnostics/forensics.
3. **Action callback payload validation is partial.**
   - Stored payload hash is computed but not revalidated against reconstructed payload on confirm.
   - Token theft risk is limited by owner id check, but hash currently provides no enforcement value.

### P1 (high regression/operability risk)
1. **Router boundary drift into a “god-router”.**
   - `owner_console.py` mixes intent parsing, formatting, transport decisions, DB session handling, audit logging, ASR orchestration, and dry-run confirmation generation.
   - Current size is manageable (259 LOC), but role mixing raises regression risk and slows isolated testing.
2. **Cross-router coupling (`actions` imports helper from `owner_console`).**
   - `actions.py` imports `format_response` from another router module.
   - Violates clean boundary (`router=wire+delegate`) and increases accidental circular-coupling risk as features grow.
3. **Session-per-step pattern for some action paths.**
   - `write_audit_event` always opens its own DB session; same user action can commit business state and audit state in separate transactions.
   - This is acceptable initially but can create observability inconsistency under failures.
4. **No explicit upstream mode branching tests.**
   - `UPSTREAM_MODE != DEMO` returns static `UPSTREAM_UNAVAILABLE`, but there is no contract test locking this behavior and no integration test for mode switch.

### P2 (medium / technical debt)
1. **No lock tests for callback literals and wiring contracts.**
   - Callback prefixes are hardcoded (`confirm:`, `cancel:`) in both routers and keyboard callsites.
2. **No schema-level indexing for audit/event query hot paths.**
   - Baseline has core tables but no indices on `occurred_at`, `event_type`, `tool`, `created_at`, `status`, which are natural operational filters.
3. **Service/repository layer is implicit, not explicit.**
   - Tool handlers access ORM directly; acceptable at current size, but can bloat handler code as domain logic grows.

## 3) Staged PR roadmap

### PR-A (P0 safety): idempotent commit hardening
- Goal: eliminate callback race regressions and ensure deterministic “already processed” outcome.
- Files:
  - `app/bot/routers/actions.py`
  - `app/actions/idempotency.py`
  - `tests/test_action_pipeline.py`
- Changes:
  - Replace check-then-insert pattern with insert-or-detect conflict strategy under one transaction path.
  - Catch uniqueness conflict and return stable UX message.
  - Add race simulation test (two confirm attempts with same key).
- Do NOT touch:
  - callback literals, env keys, tool payload contracts.

### PR-B (boundary hardening): router-only wiring contracts
- Goal: keep routers thin and prevent monolith drift.
- Files:
  - `app/bot/routers/owner_console.py`
  - `app/bot/routers/actions.py`
  - `app/bot/ui/*.py` (new helper module)
  - tests for boundary contracts.
- Changes:
  - Move `format_response`, `call_tool_handler`, and intent parsing helpers into dedicated helper/service modules with backward-compatible imports.
  - Remove router-to-router import (`actions` -> `owner_console`).
- Do NOT touch:
  - runtime behavior, response texts, callback prefixes.

### PR-C (security+audit visibility)
- Goal: improve forensics without changing access semantics.
- Files:
  - `app/bot/middlewares/owner_gate.py`
  - `app/storage/bootstrap.py` (or dedicated audit service)
  - `tests/test_owner_gate.py`
- Changes:
  - Log/audit denied access attempts with minimal payload (`user_id`, `chat_id`, `update_type`) and throttling guard.
  - Keep deny behavior unchanged.
- Do NOT touch:
  - allowlist semantics (`OWNER_IDS`) and middleware chain order.

### PR-05C status update
- ✅ Mitigated: visibility for denied access attempts (`access_denied`) is implemented in `OwnerGateMiddleware` for both message and callback flows.
- ✅ Throttling added (`deny:{update_kind}:{user_id}` with TTL) to avoid audit-table spam during repeated probes.
- ✅ Default deny UX remains silent; optional notify-once in private chat is feature-flagged (`ACCESS_DENY_NOTIFY_ONCE=false` by default).

### PR-D (contract tests / anti-regression)
- PR-05D lock-in: baseline-only policy, callback prefixes, registry contracts, no cross-router imports, and critical `ENV.example` keys are covered by static contract tests.
- Goal: lock key integration contracts from accidental drift.
- Files:
  - `tests/test_callback_contracts.py` (new)
  - `tests/test_router_wiring_contracts.py` (new)
  - `tests/test_registry_contracts.py` (new)
- Changes:
  - Lock callback prefixes (`confirm:`, `cancel:`).
  - Assert dependency bindings (registry entries not `None`, action tools have `kind="action"`).
  - Soft-file-size guard for critical routers (warn/fail threshold).

### PR-E (observability baseline)
- Goal: queryable audit logs with low-risk schema additions.
- Files:
  - `app/storage/alembic/versions/0001_baseline.py`
  - `app/storage/models.py`
  - `tests/*` for cold start.
- Changes:
  - Add additive indexes in baseline only (no new migrations).
  - Optional: if accepted, set `committed_at` on successful action commit for better timeline diagnostics.
- Do NOT touch:
  - table names/columns already used in runtime paths.

## 4) DB baseline changes (if approved)
Recommended additive-only index plan in `0001_baseline.py`:
- `ownerbot_audit_events`: index `(occurred_at)`, `(event_type, occurred_at)`.
- `ownerbot_action_log`: index `(tool, created_at)`, `(status, created_at)`, `(correlation_id)`.
- `ownerbot_demo_orders`: index `(status, created_at)`, `(flagged, flagged_at)`.
- `ownerbot_demo_chat_threads`: index `(open, last_customer_message_at)`.

Cold-start checks after baseline update:
1. Drop DB and run startup migration path.
2. Ensure seed inserts complete and bot reaches polling startup.
3. Run targeted tests for actions/tools requiring these tables.

## 5) Minimal validation commands
- `python -m compileall -q app tests`
- `pytest -q`
- `rg -n "confirm:|cancel:" app tests`
- `rg -n "from app\.bot\.routers\.owner_console import format_response" app`
- `wc -l app/bot/routers/*.py`

## 6) PR-05B boundary hardening note
- В PR-05B снижена связность роутеров: форматирование вынесено в `app/bot/ui/formatting.py`, запуск tool handlers в `app/bot/services/tool_runner.py`, rule-based intent routing в `app/bot/services/intent_router.py`.
- Убран cross-router импорт (`actions` больше не импортирует `owner_console`), что уменьшает риск циклических зависимостей и упрощает изолированные тесты.
- Изменение подготавливает безопасный фундамент для PR-06/07/08 без изменения P0 статусов.

### PR-05E perf hardening
- ✅ Добавлены baseline индексы для audit/action/demo hot paths без новых миграций.
- ✅ PR-05E снижает риск деградации производительности таблиц audit/action на production объёмах (фильтры по типу/статусу и сортировка по времени).
