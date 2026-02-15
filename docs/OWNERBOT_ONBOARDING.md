# OwnerBot onboarding (OB-ONBOARD-01)

Guided setup helps owner configure OwnerBot in minutes using Systems templates.

## What onboarding checks

`onboard_status` builds one checklist with status `ok|warn|fail`:
- SIS connectivity/preflight
- effective upstream mode + env presence flags
- SIS action capabilities (cached, no force refresh by default)
- notification settings readiness
- team routing (`MANAGER_CHAT_IDS`)

## Presets

`onboard_apply_preset` supports `dry_run -> confirm -> commit` and updates notification settings safely.

- `minimal`
  - weekly enabled (`pdf`)
  - FX apply events (failed only)
- `standard`
  - quiet digest ON
  - ops alerts ON (cooldown 8h)
  - FX delta ON (min percent 0.5, cooldown 8h)
  - weekly ON
- `aggressive`
  - daily digest (`png`)
  - tighter ops thresholds
  - FX delta more sensitive (0.25, cooldown 6h)

On successful commit onboarding stores:
- `onboard_completed_at` (once)
- `onboard_last_run_at`
- `onboard_last_status`
- `onboard_last_summary`

## Test run

`onboard_test_run` can do safe checks:
- capabilities refresh
- digest preview (`dry_run`) or explicit commit
- `notify_team` dry run preview

The tool is protected by a Redis lock + cooldown per owner to avoid spam.
