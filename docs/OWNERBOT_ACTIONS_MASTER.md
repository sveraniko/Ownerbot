# OWNERBOT Actions Master

**File:** `docs/OWNERBOT_ACTIONS_MASTER.md`  
**Role:** Source-of-truth for *all* write-capable behavior in OwnerBot (Actions / Tools / Confirm / Audit).  
**Audience:** OwnerBot devs, reviewers, Codex/Qoder prompts.  
**Non-goal:** Explaining SIS internals. (That lives in the SIS contract doc.)

---

## 1) Purpose

OwnerBot exists to help the business owner **act** without wasting cognitive bandwidth on:
- collecting numbers,
- chasing managers,
- clicking admin panels,
- repeating the same operations during chaos.

**Prime directive:**  
**Owner intuition stays in charge. OwnerBot never “decides for you”.**  
It proposes, previews, verifies, and executes *only* what you explicitly confirm.

---

## 2) System boundaries

OwnerBot is a standalone service with its own:
- runtime,
- DB,
- Redis (optional),
- audit trail.

OwnerBot can **connect to SIS** (and later other systems like SizeBot), but must remain runnable even if SIS is down.

**Key property:** *No coupling that makes OwnerBot crash because SIS was redeployed.*

---

## 3) Core invariants (do not break)

### 3.1 All write operations use the same pipeline
Any operation that changes state (SIS prices, product visibility, discounts, notifications, etc.) MUST follow:

1) **Intent → Tool plan**  
2) **Dry-run preview** (no side effects)  
3) **Confirm** (explicit user approval)  
4) **Commit** (exactly-once semantics)  
5) **Finalize + Audit + Report**

No exceptions. No “fast paths”.

### 3.2 OwnerBot never lies
- If data is missing or uncertain: say so.
- If action can’t be verified: refuse or ask for a safer alternative.
- If SIS is unreachable: do not “guess”.

### 3.3 Deterministic safety over convenience
- Double-tap on ✅ must not double-commit.
- Any corrupted confirm payload must be blocked.
- Any action must be traceable by correlation ID and audit event.

---

## 4) Terminology

- **Tool**: callable capability, either *read-only* or *action* (write).
- **Action**: a tool that can change state (requires confirm).
- **Dry-run / Preview**: tool output describing what would happen, without committing.
- **Confirm token**: short-lived record binding a preview payload to a later commit.
- **Payload hash**: integrity checksum of the confirm payload used to detect tampering.
- **Idempotency**: guarantees exactly-once commit for the same action payload.
- **Correlation ID**: trace ID spanning OwnerBot ↔ external systems (SIS).

---

## 5) Action pipeline (reference implementation)

### 5.1 High-level flow

**Input** (text or voice)  
→ **Intent recognition**  
→ **Plan** (choose template/tool + params)  
→ **Verifier** (rules/constraints)  
→ **Dry-run**  
→ **Confirm token** created  
→ User clicks ✅  
→ **Claim** idempotency (atomic)  
→ **Commit tool**  
→ **Finalize** (committed/failed)  
→ **Audit event** written  
→ **User report + (optional) notify_team**

### 5.2 Required states and user feedback

OwnerBot must return consistent UX for repeats:

- If confirm clicked while action is running:  
  **“Уже выполняется. Подожди.”**

- If confirm clicked again after success (within token TTL):  
  **“Уже выполнено.”**

- If payload hash mismatch or token invalid:  
  **“Некорректное подтверждение. Запусти действие снова.”**

### 5.3 Confirm token rules
- Tokens store: `payload`, `payload_hash`, `created_at`, `expires_at`, `action_name`, `actor_id`, `correlation_id`.
- After confirm execution, tokens are **expired**, not deleted immediately, to provide deterministic duplicate behavior for a short TTL.

### 5.4 Idempotency rules (atomic claim/finalize)
OwnerBot uses an atomic flow:

- `claim_action(...)` inserts `in_progress` record (unique key based on action + payload hash + actor + target scope).
- If insert fails due to unique constraint, fetch existing record and respond deterministically.
- `finalize_action(...)` sets terminal status: `committed` or `failed`.

**Requirement:** Tool handler must run only after claim succeeds.

---

## 6) “Metamodules” (the 6 technique slots)

OwnerBot uses modular guardrails. These are *conceptual modules* that can be implemented as pluggable steps.

### 6.1 Intent & Disambiguation
- Classify request: template match vs free-form.
- If multiple valid interpretations: ask a single clarifying question or propose 2–3 options.

### 6.2 Planning (Tool selection)
- Prefer **templates** for common business operations.
- Use free-form planning only when template can’t cover.

### 6.3 Verifier (Rules / Constraints)
Before any dry-run:
- validate parameters (ranges, types),
- check owner permissions,
- check system readiness (SIS reachable),
- enforce “no runtime nonsense” (e.g., no action without preview).

### 6.4 Provenance & Non-hallucination
Tool outputs must include provenance:
- source system (SIS/OwnerBot DEMO/etc.),
- query scope and timestamps,
- correlation_id.

### 6.5 Confidence & Risk labels
OwnerBot attaches a simple risk label for actions:
- **LOW**: notify_team, read-only reports
- **MED**: hide products by rule, discount percent
- **HIGH**: bulk price changes, reprice, rollback

Risk affects messaging, not permissions.

### 6.6 Retrospective (Post-action summary)
After commit:
- what changed,
- how many items,
- key warnings (anomaly, missing rates),
- where to rollback (if available).

---

## 7) Tool taxonomy

### 7.1 Read-only tools
Examples:
- KPI snapshot
- Orders search
- Revenue trend (chart)
- System health (SIS/OwnerBot/Redis/DB)

**Rule:** read-only tools never create confirm tokens.

### 7.2 Action tools
Examples:
- notify_team
- SIS reprice preview/apply (+rollback)
- SIS bump_all prices preview/apply
- hide products by stock threshold
- apply discount percent by stock threshold

**Rule:** any action tool must implement:
- `dry_run(params) -> preview`
- `commit(params) -> result`

---

## 8) Templates UX (no voice required)

Templates are the “buttons and inputs” layer that covers most owner workflows quickly.

### 8.1 Template groups
- **Цены**
  - bump_all (percent)
  - bump_category (percent) [later]
  - FX reprice (snapshot + markup + rounding) [via SIS]
  - rollback last reprice (if SIS supports)
- **Товары**
  - hide_by_stock (N)
  - unpublish_category [later]
- **Скидки**
  - apply_discount_percent_by_stock (N, %)
  - disable_all_discounts [later]

### 8.2 Input pattern
- Button → OwnerBot asks for number (if needed) → validates → dry-run → ✅ confirm → report.

Templates should not expose internal complexity:
- no currency math details,
- no base/vitrine comparisons,
- only preview examples and summary.

---

## 9) Voice routing

Voice is for:
- non-standard combinations,
- multi-step commands,
- “do X but exclude Y” requests.

### 9.1 Voice flow
ASR → text → run intent classifier:
1) Try template mapping.
2) If mapping fails, propose 2–3 interpretations.
3) Only then attempt free-form planning.

### 9.2 Safety for voice
- Voice cannot bypass preview/confirm.
- Voice cannot inject tools not in allowlist.

---

## 10) SIS integration (OwnerBot side)

**Contract lives here:** `docs/OWNERBOT_SIS_ACTIONS_CONTRACT.md` (must exist).  
OwnerBot treats SIS as an external system with failure modes.

### 10.1 Required headers
- `X-OWNERBOT-KEY` (shared secret)
- `X-CORRELATION-ID` (uuid)
- optional: `X-ACTOR-TG-ID`

### 10.2 Retry policy
- Retry only on transient network errors/timeouts.
- Do NOT auto-retry on validation failures or “force required” errors.
- If SIS returns partial/unknown state: mark action `failed` and require owner attention.

---

## 11) Audit & observability

### 11.1 Audit event schema (minimum)
Each committed/failed action must write an audit event including:
- `event_type` (ACTION_PREVIEW, ACTION_COMMIT, ACTION_FAIL, ACTION_ROLLBACK)
- `action_name`
- `actor_tg_id`
- `target_system` (SIS, OwnerBot)
- `payload_hash`
- `correlation_id`
- `started_at`, `finished_at`
- `summary`
- `warnings[]`

### 11.2 Logs
All tool calls must be logged with:
- correlation_id,
- action_name,
- duration_ms,
- status,
- safe error message.

No secrets in logs.

---

## 12) Error taxonomy

Use stable error codes for user messaging and tests:

- `VALIDATION_ERROR`
- `PERMISSION_DENIED`
- `SIS_UNAVAILABLE`
- `SIS_AUTH_ERROR`
- `SIS_RATE_MISSING`
- `ANOMALY_FORCE_REQUIRED`
- `PAYLOAD_TAMPERED`
- `IDEMPOTENCY_CONFLICT`
- `TOOL_EXECUTION_FAILED`

User-facing text must remain short and action-oriented.

---

## 13) How to add a new action tool (checklist)

1) **Define tool name** and params schema (pydantic/dataclass).
2) Implement `dry_run` producing:
   - affected_count
   - examples (≤5)
   - warnings
   - summary
3) Implement `commit` with:
   - correlation_id propagation
   - strict input validation
4) Integrate into tool registry.
5) Integrate into:
   - template UI OR free-form planner mapping
6) Add tests:
   - dry_run deterministic
   - commit idempotent under duplicate confirm
   - payload hash tamper blocked
7) Update docs:
   - add to tool catalog section
   - add template entry if applicable

---

## 14) “Do not do” list (common failure modes)

- Do not add “quick commit without preview”.
- Do not add hidden side effects in read-only tools.
- Do not implement “magic” currency conversion at runtime in OwnerBot. OwnerBot calls SIS actions.
- Do not let LLM output trigger commits directly.
- Do not store secrets (API keys) in DB or logs.

---

## 15) Minimal acceptance criteria for OwnerBot Actions

A change is “done” only when:
- preview works,
- confirm works,
- double confirm does not double-commit,
- audit logs are written,
- correlation_id appears in logs and external calls,
- failure states are deterministic and readable.

---

## 16) References (project docs)

- `README.md` (OwnerBot Quick Start)
- `docs/OWNERBOT_TECH_BASE.md`
- `docs/OWNERBOT_TOOLS.md`
- `docs/OWNERBOT_PROD_AUDIT.md`
- `docs/OWNERBOT_SIS_ACTIONS_CONTRACT.md` (must exist)
