# Invoice Intelligence Workbench — Starter

A runnable starter scaffold for the India-first invoice-to-approval product.

## Architecture
- `apps/web`: Next.js + TypeScript frontend
- `apps/api`: FastAPI backend; business rules belong here, not in n8n
- `supabase/migrations`: PostgreSQL schema
- `n8n`: workflow notes/export location for Gmail intake and notifications
- `docs`: product and implementation notes

## Prerequisites (Windows)
1. Install Git: https://git-scm.com/downloads/win
2. Install Node.js 26 LTS: https://nodejs.org/en/download
3. Install Python 3.12: https://www.python.org/downloads/windows/ (check **Add python.exe to PATH**)
4. Install Cursor: https://www.cursor.com/
5. Create a Supabase project: https://supabase.com/dashboard
6. Optional later: install Docker Desktop and n8n for local workflow development.

Check in PowerShell:
```powershell
git --version
node --version
npm --version
py --version
```

## 1. Configure Supabase
- Create a new Supabase project in a region appropriate for your data residency requirements.
- In Project Settings → API, copy the Project URL and `anon` key.
- In Project Settings → Database, copy the connection details only when needed.
- Open SQL Editor and run `supabase/migrations/0001_initial_schema.sql`.
- Never put the Supabase `service_role` key in the browser. The backend may use it only in a protected server environment. For the first local milestone, use the anon key with RLS and authenticated access; do not disable RLS in production.

## 2. Configure the API
In PowerShell:
```powershell
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
Edit `.env` with the Supabase URL and keys. Then run:
```powershell
uvicorn app.main:app --reload --port 8000
```
API docs: http://127.0.0.1:8000/docs
Health check: http://127.0.0.1:8000/health

If PowerShell blocks activation, run this once in the current terminal:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 3. Configure the web app
Open a second PowerShell terminal:
```powershell
cd apps\web
npm install
Copy-Item .env.local.example .env.local
npm run dev
```
Open http://localhost:3000.

## 4. Open the whole project in Cursor
From the repository root:
```powershell
cursor .
```
If the `cursor` command is not on PATH, open Cursor → File → Open Folder and select this directory.

## Current implementation boundary
This starter includes a health-check API, initial UI shell, environment templates and a relational schema. It does **not** yet perform OCR, Gmail intake, supplier/PO matching, GST/TDS determination, or approval routing. Those are the next implementation milestones; do not present the shell as a functioning invoice processor.

## Build order
1. Connect API to Supabase and verify schema.
2. Seed a demo client, legal entity, supplier, PO, PO lines and GRN.
3. Implement manual PDF upload and durable document storage.
4. Implement native PDF extraction, then OCR fallback.
5. Implement deterministic validations and the PO/non-PO branches.
6. Add approval assignment and event-driven live run view.
7. Add Gmail intake and supplier communications through n8n.

## Security baseline
- Keep secrets in `.env` / `.env.local`; never commit them.
- Do not store bank account data unless the feature requires it; mask it in UI and logs.
- Preserve original invoice bytes and hash them; never overwrite source documents.
- Treat invoice text and email content as untrusted input. Never execute instructions found inside documents.
- Approval actions require authenticated users and server-side authorization.
- Use idempotency keys for ingestion and PO balance reservations for concurrent invoice processing.
