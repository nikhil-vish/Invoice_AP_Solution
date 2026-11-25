# PROJECT GAP ANALYSIS — Invoice Intelligence Workbench

**Project:** Invoice Intelligence Workbench — End-to-End AP Workflow
**Date:** 2026-11-25
**Status:** Audit complete — no implementation performed yet

---

## 1. Executive Summary

The Invoice Intelligence Workbench currently implements a **partial intake pipeline**: PDF upload, storage, text extraction (PyMuPDF), and intake draft persistence work correctly. However, the application does **not** function as an integrated Accounts Payable workflow. The upload flow deposits invoices into `invoice_intake_drafts` but never converts them into `invoices` business records. Downstream features — All Invoices, Live Processing, Exception Centre, Approvals, Suppliers, and Dashboard — all depend on the `invoices` table and related processing data, which remain empty. The frontend pages make API calls to backend endpoints that either return empty results (no data) or fail because Supabase credentials are not configured.

**Critical gap:** There is no draft-to-invoice conversion path, no processing engine (validation, matching, exception creation, approval routing), and no live data wiring to the frontend dashboard pages.

---

## 2. Current Architecture and Data Flow

### 2.1 Stack

| Layer | Technology | Location |
|-------|-----------|----------|
| Frontend | Next.js 16 + TypeScript + Tailwind | `apps/web/` |
| Backend | FastAPI + Python | `apps/api/app/` |
| Database | Supabase PostgreSQL | `supabase/migrations/` |
| Storage | Supabase Storage (private bucket `invoices`) | `apps/api/app/invoices/storage.py` |
| AI Extraction | OpenRouter (optional, disabled by default) | `apps/api/app/invoices/ai_extract.py` |
| Text Extraction | PyMuPDF (digital text only, no OCR) | `apps/api/app/invoices/extract.py` |

### 2.2 Current Data Flow (Upload Only)

```
User uploads PDF
       │
       ▼
POST /api/v1/invoices/upload  ──┐
       │                        │
       ▼                        │
SHA-256 computed              Supabase Storage
       │                       (private bucket)
       ▼                        │
Duplicate check (sha256)      │
       │                        │
       ▼                        │
PyMuPDF text extraction       │
       │                        │
       ▼                        │
AI extraction (if enabled)    │
       │                        │
       ▼                        │
Merge results                 │
       │                        │
       ▼                        │
Insert into invoice_intake_drafts  │
       │                        │
       ▼                        │
Return draft_id to frontend   │
                              │
Return response (fields,      │
 line_items, etc.)            │
                              │
Frontend stores draft_id,     │
navigates to /review/{id}     │
                              │
GET /api/v1/invoices/drafts/{id}  ← Only active retrieval path
```

### 2.3 What Does NOT Happen After Upload

- No row is ever inserted into `public.invoices`
- No row is ever inserted into `public.processing_runs` (except via manual `/process` call)
- No exceptions are created
- No approvals are created
- No validation results are recorded
- Draft save (`POST /drafts/{id}/save`) only updates draft status to `READY_FOR_VALIDATION` — it does **not** convert to an invoice

---

## 3. Database Table Inventory and Relationships

### 3.1 Tables Created by Migrations

| Migration | Table | Purpose | RLS Enabled |
|-----------|-------|---------|-------------|
| 0001 | `public.clients` | Client master | Yes |
| 0001 | `public.client_entities` | Client entities with GSTIN | Yes |
| 0001 | `public.suppliers` | Supplier master | Yes |
| 0001 | `public.supplier_bank_accounts` | Supplier bank details | Yes |
| 0001 | `public.purchase_orders` | PO master | Yes |
| 0001 | `public.purchase_order_items` | PO line items | Yes |
| 0001 | `public.goods_receipts` | GRN records | Yes |
| 0001 | `public.goods_receipt_items` | GRN line items | Yes |
| 0001 | `public.service_entries` | Service entry records | Yes |
| 0001 | `public.contracts` | Contract master | Yes |
| 0001 | `public.budgets` | Budget/cost-centre master | Yes |
| 0001 | `public.invoices` | **Business invoice records** | Yes |
| 0001 | `public.invoice_items` | Invoice line items | Yes |
| 0001 | `public.invoice_documents` | Document storage references | Yes |
| 0001 | `public.processing_runs` | Processing run history | Yes |
| 0001 | `public.validation_results` | Validation stage results | Yes |
| 0001 | `public.exceptions` | Exception records | Yes |
| 0001 | `public.approvals` | Approval records | Yes |
| 0001 | `public.audit_logs` | Audit trail | Yes |
| 0002 | `public.invoice_intake_drafts` | Pre-identification intake drafts | Yes |
| 0002 (alter) | `public.invoices` (amounts nullable) | Made amount columns nullable | N/A |

### 3.2 Key Relationships

- `invoices.client_id` → `clients.id`
- `invoices.client_entity_id` → `client_entities.id`
- `invoices.supplier_id` → `suppliers.id`
- `invoices.purchase_order_id` → `purchase_orders.id`
- `invoice_items.invoice_id` → `invoices.id`
- `invoice_documents.invoice_id` → `invoices.id`
- `processing_runs.invoice_id` → `invoices.id`
- `validation_results.processing_run_id` → `processing_runs.id`
- `exceptions.invoice_id` → `invoices.id`
- `approvals.invoice_id` → `invoices.id`

### 3.3 Table Currently Populated by Upload Flow

| Table | Populated by Upload? | Notes |
|-------|---------------------|-------|
| `invoice_intake_drafts` | ✅ Yes | Draft persists with extracted_data JSONB |
| `invoices` | ❌ No | Never created from draft |
| `invoice_items` | ❌ No | Never created from draft |
| `invoice_documents` | ❌ No | Never created from draft |
| `processing_runs` | ❌ No | Only via manual `/process` endpoint |
| `exceptions` | ❌ No | Never created |
| `approvals` | ❌ No | Never created |

---

## 4. Backend Endpoint Inventory

| Method | Path | Function | Supabase Required? | Status |
|--------|------|----------|-------------------|--------|
| GET | `/health` | Health check | No | Working |
| GET | `/api/v1` | API info | No | Working |
| POST | `/api/v1/invoices/upload` | Upload + extract + draft | Yes | Working (if Supabase configured) |
| GET | `/api/v1/invoices` | List invoices | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/{id}` | Invoice detail | Yes | Endpoint exists, no data |
| POST | `/api/v1/invoices/{id}/process` | Start processing run | Yes | Creates run, no processing engine |
| GET | `/api/v1/invoices/runs` | List processing runs | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/runs/{id}` | Run detail | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/suppliers` | List suppliers | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/approvals` | List approvals | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/approvals/{id}` | Approval detail | Yes | Endpoint exists, no data |
| POST | `/api/v1/invoices/approvals/{id}/action` | Approval action | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/exceptions` | List exceptions | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/exceptions/{id}` | Exception detail | Yes | Endpoint exists, no data |
| POST | `/api/v1/invoices/exceptions/{id}/assign` | Assign exception | Yes | Endpoint exists, no data |
| POST | `/api/v1/invoices/exceptions/{id}/resolve` | Resolve exception | Yes | Endpoint exists, no data |
| GET | `/api/v1/invoices/drafts/{id}` | Get draft | Yes | Working (if Supabase configured) |
| POST | `/api/v1/invoices/drafts/{id}/save` | Save draft | Yes | Updates draft status only |

**Note:** All endpoints except `/health` and `/api/v1` require `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to be configured. Without these, every call returns HTTP 500.

---

## 5. Frontend Page-to-Endpoint Mapping

### 5.1 Page Inventory

| Page | Route | API Endpoints Called | Supabase Required? | Current Behavior |
|------|-------|---------------------|-------------------|------------------|
| Overview | `/` | None (static) | No | All metrics show dashes; no processing runs |
| All Invoices | `/invoices` | `GET /api/v1/invoices` | Yes | Empty — no invoices in `invoices` table |
| Upload | `/upload` | `POST /api/v1/invoices/upload` | Yes | Working if Supabase configured |
| Review | `/review/[id]` | `GET /api/v1/invoices/drafts/{id}`, `POST /drafts/{id}/save` | Yes | Working if Supabase configured |
| Live Processing | `/processing` | `GET /api/v1/invoices/runs` | Yes | Empty — no runs |
| Exception Centre | `/exceptions` | `GET /api/v1/invoices/exceptions`, `POST .../assign`, `POST .../resolve` | Yes | "Failed to load exceptions" — no exceptions data |
| Approvals | `/approvals` | `GET /api/v1/invoices/approvals`, `POST .../action` | Yes | "Failed to load approvals" — no approvals data |
| Suppliers | `/suppliers` | `GET /api/v1/invoices/suppliers` | Yes | "No suppliers found" — no supplier data |
| Settings | `/settings` | None (static) | No | Shows hardcoded status; does not query backend |

### 5.2 Exact Reasons for Observed Failures

#### Overview — Metrics display dashes
- **Root cause:** `apps/web/app/page.tsx` contains hardcoded static metric values (`"—"`). No API call is made to any backend endpoint.
- **Evidence:** `apps/web/app/page.tsx:5-10`
- **Fix:** Add `GET /api/v1/invoices` and `GET /api/v1/invoices/runs` calls to populate metrics once data exists.

#### All Invoices — Uploaded invoices absent
- **Root cause:** Upload creates rows in `invoice_intake_drafts`, not `public.invoices`. The invoices page queries `public.invoices`.
- **Evidence:** `apps/api/app/invoices/router.py:394-512` (upload inserts into `invoice_intake_drafts`), `apps/api/app/invoices/repository.py:59-93` (list queries `invoices`)
- **Fix:** Implement draft-to-invoice conversion after review/save.

#### Live Processing — No processing runs appear
- **Root cause:** Processing runs reference `invoices.id`. Since no invoices exist, no runs can exist. The `/process` endpoint creates runs but is never called automatically.
- **Evidence:** `apps/api/app/invoices/router.py:561-614` (process endpoint), `apps/api/app/invoices/repository.py:170-195` (list runs joins invoices)
- **Fix:** Auto-create processing run on draft-to-invoice conversion; implement processing engine.

#### Exception Centre — "Failed to load exceptions"
- **Root cause:** No exceptions have ever been created. The `exceptions` table is empty.
- **Evidence:** `apps/api/app/invoices/repository.py:344-375` (list queries `exceptions`)
- **Fix:** Implement exception creation during processing (missing PO, GST mismatch, etc.).

#### Approvals — "Failed to load approvals"
- **Root cause:** No approvals have ever been created. The `approvals` table is empty.
- **Evidence:** `apps/api/app/invoices/repository.py:301-330` (list queries `approvals`)
- **Fix:** Implement approval creation when invoice reaches `READY_FOR_APPROVAL`.

#### Suppliers — "No suppliers found"
- **Root cause:** No supplier master data has been seeded.
- **Evidence:** `apps/api/app/invoices/repository.py:263-296` (list queries `suppliers`)
- **Fix:** Seed supplier data or create suppliers from extracted invoice data.

#### Settings — OpenRouter shown as not configured, AI extraction disabled
- **Root cause:** `apps/api/.env` does not exist (only `.env.example`). `AI_EXTRACTION_ENABLED=false` by default. Settings page is static HTML and does not query backend config.
- **Evidence:** `apps/api/.env.example` (all keys empty), `apps/web/app/settings/page.tsx` (static status badges)
- **Fix:** Create `apps/api/.env` with actual credentials; make Settings page query backend health/config endpoint.

---

## 6. End-to-End Trace: Deccan Print & Packaging Invoice

**Reference invoice:** DPP/2026-27/0823, Supplier GSTIN: 36AABCD4512L1Z7, Buyer GSTIN: 36AABCN8901K1Z4

| Step | Expected | Actual | Gap |
|------|----------|--------|-----|
| 1. PDF upload | POST /upload returns draft_id | ✅ Works | None |
| 2. SHA-256 + storage | File stored in Supabase Storage | ✅ Works | None |
| 3. Intake/draft insertion | Row in `invoice_intake_drafts` | ✅ Works | None |
| 4. Digital text extraction | Raw text from PyMuPDF | ✅ Works (if digital PDF) | OCR not implemented for scanned |
| 5. AI structured extraction | Structured JSON from OpenRouter | ⚠️ Disabled by default | `AI_EXTRACTION_ENABLED=false`, no `.env` |
| 6. Extraction persistence | Stored in `extracted_data` JSONB | ✅ Works | None |
| 7. Review screen retrieval | GET /drafts/{id} returns data | ✅ Works | None |
| 8. Save draft | Status → READY_FOR_VALIDATION | ⚠️ Partial — status only | Does not convert to invoice |
| 9. Conversion to business invoice | Row in `public.invoices` | ❌ Never happens | **Critical gap** |
| 10. Processing run creation | Row in `public.processing_runs` | ❌ Never happens (unless manual) | **Critical gap** |
| 11. All Invoices listing | Invoice appears in table | ❌ Empty | Consequence of gap #9 |
| 12. Exception/approval creation | Rows in `exceptions`/`approvals` | ❌ Never happens | **Critical gap** |

**Missing PO handling:** PO number is genuinely absent on this invoice. Currently there is no exception created for missing PO. No validation path distinguishes PO-backed vs non-PO invoices.

---

## 7. Feature Gap Matrix

| Capability | Status | Evidence | Gap Details |
|------------|--------|----------|-------------|
| **A. Intake and document extraction** | Implemented and verified | `router.py:upload_invoice`, `extract.py` | OCR not implemented for scanned PDFs; AI extraction disabled by default |
| **B. Buyer/client entity identification** | Partially implemented | `extract.py:_party()` | Regex-based name/GSTIN split; no matching against `client_entities` table |
| **C. Supplier master and verification** | Partially implemented | `suppliers` table exists, no data | No supplier creation from extracted data; no GSTIN verification against GST portal |
| **D. Duplicate invoice detection** | Partially implemented | SHA-256 check on drafts only | Duplicate check only on `invoice_intake_drafts.sha256`, not on `invoices` (invoice_number + supplier) |
| **E. PO and invoice line matching** | Not implemented | `purchase_orders`, `purchase_order_items` tables exist but unused | No PO matching logic anywhere in codebase |
| **F. Cumulative billing / previous invoice checks** | Not implemented | No code references previous invoices | No cumulative billing tracking |
| **G. GRN matching for goods** | Not implemented | `goods_receipts` table exists but unused | No GRN-invoice matching |
| **H. Service-entry matching for services** | Not implemented | `service_entries` table exists but unused | No service-entry matching |
| **I. Non-PO invoice processing** | Not implemented | No distinction in processing path | All invoices treated the same; no PO vs non-PO branching |
| **J. GST validation** | Partially implemented | GSTIN regex in `extract.py` | Format validation only; no IRN/QR verification; no GSTIN authenticity check |
| **K. TDS rules** | Not implemented | No TDS code anywhere | Settings page lists TDS as "Not implemented" |
| **L. Budget and cost-centre validation** | Not implemented | `budgets` table exists but unused | No budget checking |
| **M. Exception creation, assignment, resolution** | Implemented but broken | `exceptions` table + endpoints exist | No exceptions are ever created during processing; frontend fails because table is empty |
| **N. Approval routing and human decisions** | Implemented but broken | `approvals` table + endpoints exist | No approvals are ever created; no routing logic |
| **O. Processing history and audit trail** | Partially implemented | `processing_runs`, `validation_results`, `audit_logs` tables exist | Runs never auto-created; validation results never inserted; audit logs only written by exception/approval actions |
| **P. Dashboard metrics and operational reporting** | Not implemented | `page.tsx` is static HTML | No metrics API; all values hardcoded as dashes |

**Status Legend:**
- Implemented and verified: Code exists and works in tests
- Implemented but broken: Code exists but fails in production due to missing data/config
- Partially implemented: Some code exists but key functionality missing
- Not implemented: No code exists for this capability
- Cannot verify: Requires live environment to confirm

---

## 8. Target Invoice Lifecycle and State Transitions

### 8.1 Separation of Concerns

| Dimension | Status Field | Table | Purpose |
|-----------|-------------|-------|---------|
| Validation | `processing_status` | `public.invoices` | Extraction, validation, matching progress |
| Approval | `approval_status` | `public.invoices` | Human approval decision progress |
| Draft | `processing_status` | `public.invoice_intake_drafts` | Pre-identification intake state |

### 8.2 Processing Status Lifecycle (Validation)

```
RECEIVED
   │ (upload complete, draft created)
   ▼
EXTRACTED
   │ (review saved, draft → invoice conversion)
   ▼
READY_FOR_VALIDATION
   │ (validation engine runs)
   ▼
VALIDATION_IN_PROGRESS
   ├─ all checks pass ──► READY_FOR_APPROVAL
   ├─ hard-stop exception ─► EXCEPTION
   └─ soft warning ───────► NEEDS_REVIEW
```

### 8.3 Approval Status Lifecycle (Human Decision)

```
PENDING
   │ (human reviews)
   ├─ APPROVE ─────────► APPROVED
   ├─ REJECT ──────────► REJECTED
   └─ RETURN_FOR_INFO ──► PENDING (stays pending, sent back for info)
```

### 8.4 Exception States

```
OPEN → AWAITING_RESPONSE → IN_REVIEW → RESOLVED → CLOSED
      ↳ ESCALATED ────────┘
```

### 8.5 State Transition Rules

| From → To | Trigger | Condition |
|-----------|---------|-----------|
| RECEIVED → EXTRACTED | Upload complete | Text extracted successfully |
| EXTRACTED → READY_FOR_VALIDATION | Draft saved | User confirms extracted data |
| READY_FOR_VALIDATION → VALIDATION_IN_PROGRESS | Processing engine starts | Validation rules begin |
| VALIDATION_IN_PROGRESS → READY_FOR_APPROVAL | All validations pass | No hard-stop exceptions |
| VALIDATION_IN_PROGRESS → EXCEPTION | Hard-stop exception found | CRITICAL severity, unresolved |
| VALIDATION_IN_PROGRESS → NEEDS_REVIEW | Soft warning | WARNING status, resolvable |
| READY_FOR_APPROVAL → PENDING_APPROVAL | Approval created | Approval record inserted |
| PENDING_APPROVAL → APPROVED | Human approves | No blocking exceptions |
| PENDING_APPROVAL → REJECTED | Human rejects | With comment |
| PENDING_APPROVAL → PENDING | Return for information | With comment, stays pending |

### 8.6 Missing PO Handling

- **PO-backed invoice** (procurement_type = 'PO'): Missing PO number → create CRITICAL exception, route to EXCEPTION, block approval
- **Non-PO invoice** (procurement_type = 'NON_PO'): Missing PO number → expected, no exception, proceed to validation
- **UNKNOWN procurement_type**: Flag for review, determine PO vs non-PO based on PO number presence

---

## 9. Prioritised Implementation Roadmap

### Phase 1: Foundation — Connect Upload to Business Records (Week 1)

| # | Task | Root Cause | Fix | Priority |
|---|------|-----------|-----|----------|
| 1.1 | Create `.env` files for API and web | No `.env` exists; Supabase/OpenRouter not configured | Create `apps/api/.env` and `apps/web/.env.local` with actual values | High |
| 1.2 | Implement draft-to-invoice conversion | Upload creates `invoice_intake_drafts` but never `public.invoices` | Add endpoint `POST /drafts/{id}/convert` that inserts into `invoices`, `invoice_items`, `invoice_documents`, creates `processing_runs` | High |
| 1.3 | Auto-create processing run on conversion | No processing runs exist | In conversion endpoint, insert `processing_runs` with status `QUEUED` | High |
| 1.4 | Fix Settings page to query backend config | Static HTML shows hardcoded status | Add `GET /api/v1/health` or config endpoint call; display actual Supabase/OpenRouter/AI status | Medium |
| 1.5 | Fix Overview page to query backend | Static metrics show dashes | Add API calls to `GET /api/v1/invoices` (count) and `GET /api/v1/invoices/runs` (count) | Medium |

### Phase 2: Processing Engine — Validation and Exceptions (Week 2)

| # | Task | Root Cause | Fix | Priority |
|---|------|-----------|-----|----------|
| 2.1 | Implement PO vs non-PO branching | No distinction in processing | In conversion, set `procurement_type` based on PO number presence; branch validation | High |
| 2.2 | Missing PO exception for PO-backed invoices | No exception created for missing PO | If `procurement_type='PO'` and `po_number` is null → create `exceptions` row with `exception_code='MISSING_PO'`, severity `CRITICAL` | High |
| 2.3 | GSTIN validation | Format-only validation | Add GSTIN checksum validation; cross-check supplier GSTIN against `suppliers` table | Medium |
| 2.4 | Arithmetic validation | No tax arithmetic check | Verify `taxable_value + cgst + sgst (+ igst) = grand_total`; create WARNING exception on mismatch | Medium |
| 2.5 | Duplicate invoice detection (invoice level) | SHA-256 only on drafts | Check `invoices` for duplicate `invoice_number` + `supplier_id` combination | Medium |
| 2.6 | Processing engine (background) | `/process` creates run but does nothing | Implement worker that processes `QUEUED` runs: validation → exceptions → approvals | High |

### Phase 3: Approval Routing (Week 3)

| # | Task | Root Cause | Fix | Priority |
|---|------|-----------|-----|----------|
| 3.1 | Auto-create approval on READY_FOR_APPROVAL | No approvals created | When validation passes and no hard-stop exceptions, insert into `approvals` with `status='PENDING'` | High |
| 3.2 | Approval action endpoints already exist | Working but no data | No code change needed once approvals exist | — |
| 3.3 | Approval blocking on hard-stop exceptions | `action_approval` already checks | Verified working in repository; no change needed | — |

### Phase 4: Matching and Advanced Validation (Week 4)

| # | Task | Root Cause | Fix | Priority |
|---|------|-----------|-----|----------|
| 4.1 | PO line matching | No matching logic | Match invoice line items against `purchase_order_items` by description/HSN; tolerance ±2% price, ±5% quantity | Medium |
| 4.2 | GRN matching for goods | No GRN logic | Match against `goods_receipts` and `goods_receipt_items` | Medium |
| 4.3 | Service-entry matching | No service logic | Match against `service_entries` | Medium |
| 4.4 | Budget/cost-centre validation | No budget logic | Check `budgets` table for cost-centre availability | Low |
| 4.5 | TDS rules | Not implemented | Add TDS applicability check based on supplier/amount thresholds | Low |

### Phase 5: Dashboard and Reporting (Week 5)

| # | Task | Root Cause | Fix | Priority |
|---|------|-----------|-----|----------|
| 5.1 | Dashboard metrics API | No metrics endpoint | Add `GET /api/v1/dashboard/metrics` returning counts by status | Medium |
| 5.2 | Frontend dashboard wiring | Static HTML | Replace hardcoded values with API data | Medium |
| 5.3 | Processing run status updates | Runs stuck at QUEUED | Processing engine updates run status to RUNNING/COMPLETED/FAILED | High |

---

## 10. Dependencies and Risks

### 10.1 Dependencies

| Dependency | Status | Risk if Missing |
|------------|--------|-----------------|
| Supabase project with all migrations applied | Not configured | All database-dependent endpoints return 500 |
| `SUPABASE_SERVICE_ROLE_KEY` | Not set | Backend cannot write to database |
| Supabase Storage bucket `invoices` | Not verified | Uploads fail |
| `OPENROUTER_API_KEY` | Not set | AI extraction disabled; regex-only extraction |
| Frontend `.env.local` with `NEXT_PUBLIC_API_BASE_URL` | Not set | Frontend cannot reach backend |
| RLS policies on Supabase tables | Not created | All RLS-enabled tables block service-role reads/writes depending on policy |

### 10.2 Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| No RLS policies → database access blocked | High | Add Supabase RLS policies before production use |
| Service-role key in frontend exposure | Critical | Settings page must never expose service-role key; backend-only config |
| AI extraction makes approval decisions | Critical | Validation status separate from approval status; AI never calls approval endpoints |
| Fabricated missing fields | High | All missing fields must remain null; never invent PO, GSTIN, or amounts |
| Draft-to-invoice data loss | Medium | Conversion must preserve all extracted fields; missing fields flagged, not dropped |
| Duplicate processing runs | Medium | Idempotency key on `processing_runs`; check existing QUEUED/RUNNING before creating |

---

## 11. Files Changed in This Audit (Read-Only)

No files were modified during this audit. The following files were inspected:

**Backend:**
- `apps/api/app/main.py`
- `apps/api/app/config.py`
- `apps/api/app/invoices/router.py`
- `apps/api/app/invoices/repository.py`
- `apps/api/app/invoices/extract.py`
- `apps/api/app/invoices/records.py`
- `apps/api/app/invoices/fields.py`
- `apps/api/app/invoices/models.py`
- `apps/api/app/invoices/ai_extract.py`
- `apps/api/app/invoices/storage.py`
- `apps/api/.env.example`
- `apps/api/tests/test_upload.py`
- `apps/api/tests/test_ai_extract.py`
- `apps/api/tests/test_indian_gst_invoice.py`
- `apps/api/pytest.ini`

**Database:**
- `supabase/migrations/0001_initial_schema.sql`
- `supabase/migrations/0002_invoice_intake_drafts.sql`
- `supabase/migrations/0002_nullable_extracted_amounts.sql`

**Frontend:**
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/upload/page.tsx`
- `apps/web/app/review/[id]/page.tsx`
- `apps/web/app/invoices/page.tsx`
- `apps/web/app/processing/page.tsx`
- `apps/web/app/exceptions/page.tsx`
- `apps/web/app/approvals/page.tsx`
- `apps/web/app/suppliers/page.tsx`
- `apps/web/app/settings/page.tsx`
- `apps/web/components/Shell.tsx`
- `apps/web/.env.local.example`
- `apps/web/app/globals.css`

---

**Next Step:** Review this gap analysis with stakeholders, then implement Phase 1 (Foundation) before proceeding to subsequent phases. No implementation should begin until this audit is signed off.