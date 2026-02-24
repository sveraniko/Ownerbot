# OWNERBOT_QUALITY

## Quality header
OwnerBot now prepends a compact quality line to ADVICE and TOOL responses:

`🧭 Качество: <HIGH|MED|LOW> | 📌 <DATA|HYPOTHESIS|MIXED> | ⚠️ <count>`

## Rules summary
- **TOOL**: verifier uses response status, provenance (`sources/window`), warnings, and empty data checks.
- **ADVICE**: always treated as **hypothesis**; confidence is mapped from LLM confidence (`>=0.75 high`, `>=0.45 med`, else low).
- Advice includes quality warnings when verification plan/tools are missing, and flags possible invented metrics.

## Provenance line
For tool responses OwnerBot adds a compact provenance snippet:
- source list (short)
- key window
- `as_of`

## Important policy
ADVICE is hypothesis-only and must be validated with tools (buttons `Проверить данными`).
Verifier annotates responses and does not block normal execution.
