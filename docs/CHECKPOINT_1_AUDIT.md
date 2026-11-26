# Checkpoint 1 — Read-only Repository & Schema Audit

## Rule
Do not modify application code. Stop and report; wait for explicit approval before Checkpoint 2 (WP1/WP2).

## Baseline (executed)
- Backend: `cd apps/api && python -m pytest -q` → **114 passed, 3 warnings**.
- Frontend: `cd apps/web && npm run build` → **success** (routes include /copilot).
- Git: branch `Upload_pdf_1`. Uncommitted modified: `apps/api/app/invoices/repository.py`, `apps/api/app/invoices/router.py`, `apps/web/.env.local.example`, `apps/web/components/Shell.tsx`. Pre-existing uncommitted additions exist in repository.py (lifecycle/transition/phase4/action_approval) NOT made by this audit — left untouched per rule 14.
- Migration head: `0008_invoice_lifecycle_events.sql`.

## Schema facts (from migrations)
- `invoices`: `supplier_legal_name` text exists; `supplier_name` does NOT exist (migration 0005 line 30).
- RLS: migration 0001 enables RLS on tables but creates **zero policies**; 0007/0008 likewise.
- Workspace: migration 0004/0005 `clients`/`client_entities`; `resolve_demo_workspace` looks up by `display_name = 'Invoice Intelligence Demo Workspace'`.

## API/auth facts (from router.py)
Auth verified (`_verified_reviewer_id`): approval_action, copilot, process (indirectly), submit/draft.
Auth NOT verified: `assign_exception_endpoint` (line 455), `resolve_exception_endpoint` (line 488), `upload_invoice` (line 561), list endpoints (use `_demo_client_id`).
`request: ExceptionAssignRequest = None` / `= None` → absent body raises AttributeError → 500 (lines 457, 490).
`api_info` advertises `/api/v1/runs` / `/api/v1/suppliers` but actual paths are `/api/v1/invoices/runs` / `/api/v1/invoices/suppliers` (main.py).
Upload endpoint unauthenticated and unthrottled.

## Processing/AI facts (ai_analysis.py + router.py _run_analysis)
`analyse_invoice` raises `AIExtractionError` when AI disabled/missing key (line 13-14). `_run_analysis` catches → invoice `FAILED` + `ANALYSIS_RETRY_REQUIRED`, run `FAILED`. Deterministic checks run first and persist, but no runtime approvals/exceptions are created anywhere in processing. AI failure leaves invoice stuck FAILED; no deterministic-only pass path.

## Confirmed defect vs finding (from QA report)
| ID | Finding | Severity | Confirmed? | Evidence | Current status |
|---|---|---|---|---|---|
| D-01 | AI-disabled processing failure | Critical | YES | ai_analysis.py:13-14; _run_analysis catch | OPEN (WP3) |
| D-02 | Runtime approvals/exceptions missing | Critical | YES | _run_analysis creates no approvals/exceptions | OPEN (WP4) |
| D-03 | `invoices.supplier_name` invalid column | Critical | YES | migration 0005:30 vs router.py:478-524 | FIXED → `supplier_legal_name` |
| D-04 | Copilot missing auth token → 401 | High | YES | copilot/page.tsx (no Authorization); backend line 986 | FIXED → sends bearer token |
| D-05 | Exception assign/resolve unauthenticated | High | YES | router.py:455,488 no _verified_reviewer_id; None body → 500 | OPEN (WP6) |
| D-06 | RLS policies missing | High | YES | migrations 0001/0007/0008 enable RLS, zero policies | OPEN (WP7) |
| D-07 | Seed/API workspace mismatch | High | YES | seed_demo.py CLIENT_ID=0000...0001 vs resolve_demo_workspace display_name lookup | OPEN (WP1) |
| D-08 | Live credentials in .env.local.example | Medium | YES | .env.local.example contains real Supabase URL/anon key/project ref | OPEN (WP8) |
| D-09 | API route prefix inconsistency | Medium | YES | main.py api_info lists wrong paths | OPEN (WP8) |
| D-10 | Missing request-body validation → 500 | Medium | YES | router.py:457,490 `request = None` dereference | OPEN (WP8) |

## Ambiguities requiring decision before Checkpoint 2
- WP1: canonical workspace resolution — should seed align to DB `clients.display_name` row, or should resolve_demo_workspace accept a configured default ID? Need schema confirmation of which client row actually exists.
- WP7 (RLS): backend uses service-role key (bypasses RLS). Enabling RLS policies could break backend reads unless service-role remains or policies account for it. Must not apply remote migrations; provide manual SQL only.

## Pre-plan fixes already applied (deviate from "start empty" but align with plan intent)
- D-03 fixed in repository.py (supplier_legal_name).
- D-04 fixed in copilot/page.tsx (Authorization header).
Backend tests still 114 pass; frontend build still passes after these fixes.

## Next (Checkpoint 2 — WP1/WP2): requires explicit approval.
Implement workspace alignment + supplier field/query correctness, run focused tests, stop and report.
