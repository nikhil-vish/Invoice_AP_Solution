# Invoice Intelligence Workbench

An end-to-end Accounts Payable invoice processing workbench: upload PDFs → extract fields (regex + optional OpenRouter AI) → deterministic GST/tax validation → human review/editing → approval workflow → exceptions → audit trail.

## Architecture

```
Frontend (Next.js App Router) → FastAPI (Port 8000) → Supabase Service Role → PostgreSQL
                                                  ↳ Supabase Storage (private bucket 'invoices')
                                                  ↳ OpenRouter API (optional AI extraction/analysis)
```

| Layer | Technology | Location |
|-------|-----------|----------|
| Frontend | Next.js 16 + React + TypeScript + Tailwind (App Router) | `apps/web/` |
| Backend | FastAPI + Python | `apps/api/` |
| Database | Supabase PostgreSQL (with RLS) | `supabase/migrations/` |
| Storage | Supabase Storage (private bucket `invoices`) | — |
| AI Provider | OpenRouter (optional, disabled by default) | — |
| Email Intake | Python IMAP poller (n8n alternative) | `tools/email_uploader.py` |

## Features Implemented

- **Invoice upload** (PDF, max 15 MB) with SHA-256 deduplication
- **Text extraction** via PyMuPDF (digital text); regex-based field parsing
- **Optional AI extraction** via OpenRouter (disabled by default; requires API key)
- **Draft review & edit** of all extracted fields and line items
- **Deterministic validation**: GSTIN checksum, tax reconciliation, line-item reconciliation, duplicate detection
- **PO matching**: header amount, line quantities, unit prices, payment terms, supplier amount anomaly
- **Processing runs** with idempotency and status tracking (DRAFT → SUBMITTED → PROCESSING → PENDING_APPROVAL → APPROVED/REJECTED)
- **Human approval workflow** (Approve / Reject / Return for Info) with comment requirements
- **Exception management** (Open / In Review / Resolved / Escalated) with auto-routing to approvals when all exceptions are cleared
- **Supplier management** with PO number linkage
- **Dashboard metrics** (operational + financial + AI intelligence)
- **AI Copilot** for invoice Q&A (requires OpenRouter credentials)
- **Audit trail**: lifecycle events + audit logs
- **Email-to-invoice ingestion**: Python IMAP poller that reads email attachments and uploads them to the API

---

## Prerequisites (Windows)

1. **Git**: https://git-scm.com/downloads/win
2. **Node.js 26 LTS**: https://nodejs.org/en/download
3. **Python 3.12**: https://www.python.org/downloads/windows/ (check **Add python.exe to PATH**)
4. **Cursor** (optional): https://www.cursor.com/
5. **Supabase account**: https://supabase.com/dashboard

Verify in PowerShell:
```powershell
git --version
node --version
npm --version
py --version
```

---

## Quick Start

### Step 1: Configure Supabase

1. Create a new Supabase project at https://supabase.com/dashboard
2. In **Project Settings → API**, copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `SUPABASE_ANON_KEY` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - **service_role** key → `SUPABASE_SERVICE_ROLE_KEY` (backend only)
3. In the Supabase **SQL Editor**, run all migrations in order:
   ```sql
   -- Run these files in numerical order:
   supabase/migrations/0001_initial_schema.sql
   supabase/migrations/0002_invoice_intake_drafts.sql
   supabase/migrations/0002_nullable_extracted_amounts.sql
   supabase/migrations/0003_draft_conversion_tracking.sql
   supabase/migrations/0004_processing_status_enums.sql
   supabase/migrations/0005_demo_workspace_seed.sql
   supabase/migrations/0006_processing_enums_ext.sql
   supabase/migrations/0007_ai_analyses.sql
   supabase/migrations/0008_lifecycle_events.sql
   supabase/migrations/0009_rls_policies.sql
   supabase/migrations/0010_submission_status.sql
   ```
4. Create a **private Storage bucket** named `invoices` in Supabase Storage.
5. Optional: Seed demo data:
   ```powershell
   cd apps/api
   .\.venv\Scripts\python.exe seed_demo.py
   ```

> ⚠️ Never commit `.env` or `.env.local` files containing real keys.

### Step 2: Configure the Backend (FastAPI)

Open PowerShell:
```powershell
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `apps/api/.env` with your Supabase credentials. Key settings:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server-side only) |
| `SUPABASE_STORAGE_BUCKET` | Storage bucket name (e.g., `invoices`) |
| `OPENROUTER_API_KEY` | OpenRouter API key (from https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | OpenRouter model (e.g., `nvidia/nemotron-3.5-super-vl:free`) |
| `AI_EXTRACTION_ENABLED` | Set to `true` to enable AI extraction |

Start the API:
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify: http://localhost:8000/health  
API docs: http://localhost:8000/docs

If PowerShell blocks script activation:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Step 3: Configure the Frontend (Next.js)

Open a second PowerShell terminal:
```powershell
cd apps\web
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

Edit `apps/web/.env.local` with your Supabase URL and anon key. Open http://localhost:3000.

---

## Running the Application

### Local Services

| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | http://localhost:8000 | FastAPI backend |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Health | http://localhost:8000/health | Health check |
| Frontend | http://localhost:3000 | Next.js web app |
| Dashboard | http://localhost:3000 | Invoice overview & metrics |
| Upload | http://localhost:3000/upload | PDF invoice upload |
| All Invoices | http://localhost:3000/invoices | Invoice register |
| Review | http://localhost:3000/review/[id] | Field editing & submission |
| Approvals | http://localhost:3000/approvals | Approve/reject/return invoices |
| Exceptions | http://localhost:3000/exceptions | Exception resolution |
| Suppliers | http://localhost:3000/suppliers | Supplier & PO management |
| Processing | http://localhost:3000/processing | Processing run history |
| Copilot | http://localhost:3000/copilot | AI invoice Q&A |
| Settings | http://localhost:3000/settings | Configuration status |

### Demo Flow (Happy Path)

1. **Upload** an invoice PDF at `http://localhost:3000/upload`
2. **Review** extracted fields at `http://localhost:3000/review/[id]` — fix any missing values
3. **Save draft** → **Submit for processing**
4. **Approvals** at `http://localhost:3000/approvals` — sign in (Supabase Auth), then **Approve**
5. **Dashboard** at `http://localhost:3000` — see updated metrics

**Note:** The upload endpoint works without authentication for local testing (a known security finding to address before production).

### Demo Edge Cases

1. **Validation Failure → Exception → Resolution → Approval**: Upload an invoice with a tax mismatch (e.g., CGST ≠ taxable × rate). It lands in **Exceptions** → resolve → auto-routes to **Approvals**.
2. **CRITICAL Exception Blocks Approval**: Upload a duplicate invoice (same supplier GSTIN + invoice number). Even **Hard Approve** is blocked until the CRITICAL exception is resolved.
3. **AI Extraction Disabled → Regex Fallback**: Without a valid OpenRouter key, AI extraction fails gracefully and regex-only extraction is used (fewer fields extracted).
4. **Hard Approve Override**: When validation fails but no CRITICAL exceptions exist, clicking **Approve** shows a **Hard Approve Override** dialog — confirm to approve despite validation failures.
5. **Token Expiration**: Supabase JWTs expire; the UI clears stale tokens and re-prompts for sign-in on 401 responses.

---

## Email-to-Invoice Ingestion (n8n Alternative)

Docker is not required. A Python IMAP poller reads email attachments and uploads them to the API:

```powershell
cd tools
Copy-Item .env.example .env
# Edit .env with your email credentials (use an App Password for Gmail)
..\apps\api\.venv\Scripts\python.exe email_uploader.py
```

The poller checks your inbox every 60 seconds for unread emails with PDF attachments and POSTs them to `http://localhost:8000/api/v1/invoices/upload`.

---

## Testing

Backend tests (pytest):
```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest -q
```
Expected: **114 passed** (1 skipped — live OpenRouter test requires API credentials)

Frontend build:
```powershell
cd apps/web
npm run build
```

---

## Project Structure

```
Invoice_AP_Solution/
├── apps/api/                  # FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI app, routes
│   │   ├── invoices/
│   │   │   ├── router.py      # All API endpoints
│   │   │   ├── repository.py  # Supabase data access
│   │   │   ├── extract.py     # PyMuPDF text extraction
│   │   │   ├── ai_extract.py  # OpenRouter extraction adapter
│   │   │   ├── ai_analysis.py # OpenRouter advisory analysis
│   │   │   ├── validation.py  # Deterministic GST/financial rules
│   │   │   ├── matching.py    # PO/line matching
│   │   │   ├── storage.py     # Supabase Storage
│   │   │   ├── copilot.py     # OpenRouter Q&A
│   │   │   └── fields.py, models.py, records.py
│   │   └── tests/             # Pytest test suite
│   ├── seed_demo.py           # Demo data seeder
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Backend env template
├── apps/web/                  # Next.js frontend
│   ├── app/
│   │   ├── page.tsx           # Dashboard
│   │   ├── upload/page.tsx    # Invoice upload
│   │   ├── invoices/page.tsx  # Invoice register
│   │   ├── review/[id]/page.tsx  # Field review & editing
│   │   ├── approvals/page.tsx  # Approval workflow
│   │   ├── exceptions/page.tsx  # Exception management
│   │   ├── suppliers/page.tsx  # Supplier & PO management
│   │   ├── processing/page.tsx  # Processing runs
│   │   ├── settings/page.tsx   # Configuration status
│   │   └── copilot/page.tsx   # AI copilot Q&A
│   ├── components/Shell.tsx   # Sidebar + layout
│   ├── package.json           # Node dependencies
│   └── .env.local.example     # Frontend env template
├── supabase/migrations/       # Database schema (0001–0010)
├── tools/email_uploader.py    # IMAP email-to-invoice poller
├── docs/                      # Product & implementation notes
└── README.md                  # This file
```

---

## Security Notes

- Keep secrets in `.env` / `.env.local`; never commit them
- The backend uses the Supabase service-role key (server-side only)
- The frontend uses the Supabase anon key for Auth only; all data access goes through the FastAPI backend
- Upload endpoint is unauthenticated in local dev — secure before production
- Approval actions require a valid Supabase Auth JWT
- AI prompts treat invoice text as untrusted data; no prompt-injection passthrough

---

## Support

- Docs: `docs/` directory (QA reports, decisions, gap analysis)
- API docs: http://localhost:8000/docs (when backend is running)