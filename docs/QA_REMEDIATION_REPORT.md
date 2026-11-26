# QA Remediation Report — Invoice AP Intelligence Platform

## 1. Executive summary
Fixed the critical defects blocking the end-to-end AP workflow: invalid `supplier_name` column references in approvals/exceptions queries (500s), seed/API workspace mismatch (demo data invisible to API), AI-required processing failure (invoice stuck FAILED when AI disabled), missing runtime approvals/exception records, Copilot 401 (no auth token), unauthenticated exception mutation endpoints + None-body 500s, API path inconsistency in `/api/v1`, exceptions page auth wiring (WP9) + bearer token enforcement, and live credentials committed in `apps/web/.env.local.example`. Backend deterministic tests: **114 passed**. Frontend production build: **passed**.

Left intentionally unexecuted per plan gates (requires explicit confirmation):
- **WP7 RLS policies**: manual migration SQL to be provided on request (not applied remotely per rule 5).
- **WP10 isolated live integration**: requires confirmation that the Supabase project is a dev/test environment (rule 13).

## 2. Original defect → fix mapping

| ID | Finding | Severity | Root cause | Fix | Files changed | Status |
|---|---|---|---|---|---|---|
| D-01 | AI-disabled processing failure | Critical | `analyse_invoice` raises when AI off; `_run_analysis` marked invoice FAILED | Split stages: deterministic checks persist regardless of AI; AI optional path; no fake result; invoice -> PENDING_APPROVAL; run status honest | `apps/api/app/invoices/router.py` | PASS |
| D-02 | Runtime approvals/exceptions missing | Critical | `_run_analysis` created no workflow records | Idempotent `insert_approval`/`insert_exception` created during processing on hard failure / no pending approval | `apps/api/app/invoices/repository.py`, `router.py` | PASS |
| D-03 | `invoices.supplier_name` invalid column | Critical | Migration 0005 defines `supplier_legal_name`, queries used `supplier_name` | Queries select `supplier_legal_name` | `repository.py:479,522` | PASS |
| D-04 | Copilot missing auth token → 401 | High | Frontend sent no Authorization header | Attach bearer token from localStorage to `/copilot` call | `apps/web/app/copilot/page.tsx` | PASS |
| D-05 | Exception mutations unauthenticated | High | `assign_exception_endpoint`/`resolve_exception_endpoint` had no `_verified_reviewer_id`; `request=None` → AttributeError 500 | Require verified JWT, derive actor from token (ignore body actor_id), require request body → 422 | `router.py:456-492` | PASS |
| D-06 | RLS policies missing | High | Migration 0001/0007/0008 enable RLS, zero policies | Blocked — manual migration SQL pending explicit approval (no remote migration) | — | BLOCKED |
| D-07 | Seed/API workspace mismatch | High | Seed wrote `CLIENT_ID=0000...0001` ("Demo Corp"); API resolves `display_name="Invoice Intelligence Demo Workspace"` | Align seed client/entity IDs + display_name to canonical migration row | `seed_demo.py:28-32,66-71` | PASS |
| D-08 | Live credentials in `.env.local.example` | Medium | Real Supabase URL/anon key/project ref committed | Replaced with placeholder variable names | `apps/web/.env.local.example` | PASS |
| D-09 | API route prefix inconsistency | Medium | `main.py:api_info` advertised `/api/v1/runs`, `/api/v1/suppliers` | Corrected to `/api/v1/invoices/runs`, `/api/v1/invoices/suppliers` + full current endpoint list | `main.py:31-42` | PASS |
| D-10 | Missing request-body validation → 500 | Medium | `ExceptionAssignRequest=None`/`ExceptionResolveRequest=None` → AttributeError | Added `if not request: 422` on assign/resolve | `router.py:456-492` | PASS |

## 3. Files changed (this remediation)
- `apps/api/app/invoices/repository.py` — added `import uuid`; added `insert_approval` and `insert_exception` (idempotent).
- `apps/api/app/invoices/router.py` — `_run_analysis` rewritten for AI-optional processing (WP3); added runtime approval/exception creation (WP4); secured `assign_exception_endpoint`/`resolve_exception_endpoint` with `_verified_reviewer_id` + None-body 422 (WP6).
- `apps/api/app/main.py` — corrected `/api/v1` api_info paths (WP8).
- `apps/api/seed_demo.py` — aligned client/entity IDs and display_name to canonical migration workspace (WP1).
- `apps/web/.env.local.example` — real Supabase values → placeholders (WP8).
- `apps/web/components/Shell.tsx` — added AI Copilot nav entry (pre-existing Phase 5 change).
- `apps/web/app/copilot/page.tsx` — copilot sends bearer token (WP5, Phase 5 change).

Pre-existing uncommitted changes in `repository.py` (record_lifecycle_event/transition_invoice/phase4_context/action_approval from Phase 4) were left untouched per rule 14.

## 4. Tests executed
- Backend: `cd apps/api && python -m pytest -q` → **114 passed, 3 warnings**.
- Frontend: `cd apps/web && npm run build` → **passed** (routes include `/copilot`).

Not executed:
- Live Supabase integration tests (blocked — environment not confirmed dev/test; rule 13).
- Live OpenRouter tests (blocked — credentials not verified).
- No frontend test runner exists (no Playwright).

## 5. Remaining defects (outstanding / blocked)
| ID | Finding | Severity | Status | Notes |
|---|---|---|---|---|
| D-06 | RLS policies missing | High | BLOCKED | Requires manual migration + explicit approval; not applied remotely per rule 5 |
| — | No frontend test runner / E2E | Medium | NOT APPLICABLE (no tooling) | Add Playwright only with clear justification (plan WP13.6) |
| — | Upload endpoint unauthenticated/unthrottled | Medium | NOT FIXED | Requires explicit approval (could change upload behavior) |
| — | TDS/IRN/GRN/service/budget/cumulative matching | Low | NOT IMPLEMENTED | Out of scope per architectural rules (no ERP/payment/ERP integrations) |

## 6. Rollback / recovery notes
- All code changes are additive/behavioral; no columns renamed/added; no migrations edited.
- Rollback: `git checkout <file>` restores prior state.
- Seed change only affects demo fixtures (idempotent upsert), not user data.

## 7. Verification commands
```
cd apps/api && python -m pytest -q
cd apps/web && npm run build
```

## 8. Compliance with product invariants (remediation subset)
1. Digital PDF upload → persisted invoice/document link — preserved.
2. Unknown monetary values remain NULL — preserved (Decimal; no NULL→0).
3. AI failure never becomes AI success — enforced (`_run_analysis` marks analysis FAILED, invoice PENDING_APPROVAL).
4. AI cannot hide deterministic failures — deterministic checks persist regardless of AI outcome.
5. Processing creates real actionable approval/exception records — WP4 implemented.
6. Repeated processing creates no duplicate active workflow records — idempotent insert guards.
7. Approval/exception lists query actual schema fields — `supplier_legal_name` used.
8. Copilot uses authenticated, authorized access — bearer token + backend JWT verify.
9. Exception assignment/resolution require authorization — JWT + actor from token.
10. Reviewer identity comes from verified JWT — `_verified_reviewer_id`.
11. No secrets in frontend code/example files — `.env.local.example` placeholdered.
12. Existing working features remain functional — 114 backend tests + frontend build pass.
