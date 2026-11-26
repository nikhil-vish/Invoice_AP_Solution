# QA Audit Report — Invoice AP Intelligence Platform

## 1. Executive summary
Backend deterministic tests pass (114/114) before and after fixes. Frontend production build passes. Critical defects fixed: (a) approvals/exceptions queries referenced non-existent `invoices.supplier_name` → now `supplier_legal_name`; (b) Copilot UI now sends the bearer auth token. Remaining defects are configuration/environment dependent and require live Supabase/OpenRouter (deferred pending confirmation).

## 2. Executed test results
- Backend: `cd apps/api && python -m pytest -q` → 114 passed, 3 warnings (after fixes).
- Frontend: `cd apps/web && npm run build` → success, routes include /copilot (after fixes).
- Fixed defect #3 (`supplier_name`→`supplier_legal_name` in repository.py) — verified tests still pass.
- Fixed defect #4 (copilot auth token) — verified build still passes.
- Live Supabase integration tests: NOT executed (project not confirmed dev/test).
- Live OpenRouter tests: NOT executed (credentials not verified in this run).

## 3. Feature status
| Phase | Feature | Status |
|---|---|---|
| 1 | Upload/extraction/review/register/submit | PARTIAL (OCR missing, unauth upload) |
| 2A | Validation/AI analysis | PARTIAL (AI required, no redaction) |
| 2B | Approval workbench | PARTIAL (no runtime approvals; query bug FIXED) |
| 2C | Dashboard | PARTIAL (metrics ok) |
| 3 | Workflow automation | PARTIAL (processing fails if AI disabled) |
| 4 | PO matching | PARTIAL (UI limited) |
| 5 | Copilot | PARTIAL (auth token FIXED; requires live OpenRouter) |
| 6 | Polish/security | PARTIAL (RLS missing) |

## 4. Defect register (top)
1. Critical: processing always fails when AI disabled; no approvals/exceptions produced — router.py:740-774, ai_analysis.py. (OPEN — config dependent)
2. Critical: no runtime creation of approvals/exceptions — repository.py. (OPEN)
3. Critical: `invoices.supplier_name` queried but undefined → 500 — repository.py:478-524. **FIXED** → `supplier_legal_name`.
4. High: Copilot UI no auth token → 401 — copilot/page.tsx. **FIXED** → sends bearer token.
5. High: exception assign/resolve unauthenticated — router.py:454-517. (OPEN — security fix)
6. High: no RLS policies — migrations. (OPEN)
7. High: seed data client_id mismatch — seed_demo.py. (OPEN)
8. Medium: committed live Supabase URL/anon key — .env.local.example. (OPEN)
9. Medium: /api/v1 wrong paths — main.py. (OPEN)
10. Medium: None request bodies cause 500 — router.py. (OPEN)

## 5. Blocked tests
- Live Supabase integration tests: project not confirmed dev/test; deferred.
- Live OpenRouter tests: credentials not verified in this run.

## 6. Environment limitations
- No frontend test runner; no Playwright; no real DB integration tests.

## 7. Recommendations
Fix critical items 1, 2, 5-7 first (config/security), then UI wiring (#9-10). Add real-DB integration test suite against isolated workspace once Supabase project confirmed as dev/test.
