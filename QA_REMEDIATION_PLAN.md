# Invoice AP Intelligence Platform

# QA Remediation & Safe Implementation Specification

**Document type:** Engineering remediation plan and Cursor
implementation specification\
**Scope:** Fix the defects identified in the QA audit across Phases
1--6\
**Repository:** `Invoice_AP_Solution`\
**Execution model:** Sequential, checkpointed implementation

## 0. Purpose and operating rules

This document turns the QA report into an implementation plan for
Cursor. The QA report establishes:

-   Backend deterministic tests: **114 passed**, 3 warnings.
-   Frontend production build: **passed**.
-   The full AP workflow does not reliably complete.
-   Processing can fail when OpenRouter AI is disabled.
-   Runtime approval and exception records are not being created.
-   Approval/exception queries reportedly reference
    `invoices.supplier_name`, which does not exist.
-   Copilot calls receive HTTP 401 because the frontend does not send an
    authentication token.
-   Exception assignment/resolution endpoints are reportedly
    unauthenticated.
-   RLS policies are reportedly missing.
-   Demo seed data uses a `client_id` different from the API's.
-   Live Supabase and OpenRouter integrations were not verified.
-   No frontend test runner, Playwright setup, or real-database
    integration suite was available in that QA run.

**Re-verify every finding against the current repository before
editing.** The report is evidence of observed symptoms, not a complete
root-cause analysis.

### Non-negotiable rules

1.  Inspect before editing.
2.  Preserve working Phase 1--4 functionality.
3.  Do not rebuild or replace the architecture.
4.  Do not rename/add columns based only on assumptions.
5.  Do not apply migrations remotely or automatically.
6.  Do not use production data for destructive tests.
7.  Do not print, commit, or expose secrets.
8.  Do not disable authentication, RLS, or validation to make tests
    pass.
9.  Do not create fake approvals, exceptions, or metrics.
10. The LLM must never make final approval/rejection decisions.
11. Missing monetary values must remain NULL, not become zero.
12. Mocked tests must never be reported as live integration success.
13. Make one logical change at a time and run focused tests after it.
14. Preserve uncommitted user work. Never reset, clean, or overwrite it.
15. If a business rule or schema detail is unclear, stop and report the
    ambiguity.

## 1. Target workflow and product invariants

The intended workflow is:

``` text
PDF upload
  → Text extraction and AI field extraction
  → Human review and correction
  → Save draft
  → Submit
  → Deterministic validation
  → Optional AI analysis
  → Persist findings and actionable workflow item
  → Human review / exception / clarification
  → Authenticated human decision
  → Persisted decision and audit trail
  → Dashboard reflects persisted outcomes
```

Use the actual existing status enum and database constraints. Do not
introduce a competing status vocabulary.

  Activity                            Authority
  ----------------------------------- --------------------------------------
  Extract invoice fields              LLM with schema validation
  Tax/total arithmetic                Deterministic Python using `Decimal`
  GSTIN syntax/checksum               Deterministic backend code
  Exact duplicate key                 Deterministic backend code
  Contextual anomaly identification   LLM may assist
  Explain discrepancies               LLM, grounded in evidence
  Recommend an action                 LLM, advisory only
  Assign reviewer                     Backend workflow rules
  Approve/reject                      Authenticated, authorised human
  Persist decision/audit              Backend/database

AI provider outage must not erase deterministic results, become false AI
success, or result in approval.

## 2. Execution order

  -----------------------------------------------------------------------
  Work package            Scope                   Exit condition
  ----------------------- ----------------------- -----------------------
  WP0                     Read-only               Actual schema, routes,
                          repository/schema audit auth, workspace map

  WP1                     Canonical workspace     Seed and API use same
                          resolution              valid workspace

  WP2                     Supplier field/query    Approval/exception
                          correction              lists no longer 500

  WP3                     AI-optional processing  Deterministic checks
                                                  run with AI disabled

  WP4                     Runtime                 Processing creates
                          approvals/exceptions    real, idempotent
                                                  workflow records

  WP5                     Copilot authentication  Valid session token
                                                  reaches protected API

  WP6                     Exception endpoint      Mutations require
                          authorization           authorized reviewer

  WP7                     RLS/storage security    Policies tested without
                                                  breaking valid flows

  WP8                     Config, routing,        Correct paths and
                          request validation      controlled 4xx errors

  WP9                     Frontend wiring         Screens use persisted
                                                  data and correct auth

  WP10                    Isolated                Core lifecycle passes
                          integration/E2E tests   safely

  WP11                    Final regression/report Evidence-based final QA
                                                  report
  -----------------------------------------------------------------------

Do not start RLS changes before understanding current service-role and
user-token access patterns.

------------------------------------------------------------------------

# 3. WP0 --- Read-only repository and schema audit

## 3.1 Inspect relevant code

Backend: - `apps/api/app/main.py` - `apps/api/app/invoices/router.py` -
`apps/api/app/invoices/repository.py` -
`apps/api/app/invoices/ai_analysis.py` - Extraction/OpenRouter modules -
Authentication/JWT verification - Approval and exception services - PO
matching services - Copilot routes/services - Settings/configuration -
Background processing/run implementation

Frontend: - `apps/web/app/approvals/page.tsx` -
`apps/web/app/exceptions/page.tsx` - `apps/web/app/copilot/page.tsx` -
Invoice register and processing pages - Supabase browser client - API
client/helper - Session/auth handling - Shared navigation and status
components

Database: - Every file under `supabase/migrations/` - Invoice and
intake-draft tables - Invoice line items - Processing runs - AI
analyses - Approvals - Exceptions - Audit/events - Client/workspace
tables - PO and PO line-item tables - RLS policies - Storage bucket and
policies

## 3.2 Produce a schema map

For each relevant table, record: - Exact table name and columns. - Types
and nullability. - Primary and foreign keys. - Unique/check
constraints. - Indexes. - RLS enabled/disabled and policy names. -
Repository methods that read/write it.

Do not infer physical columns from TypeScript or Pydantic models. Verify
migrations and, if authorised, read-only live schema.

## 3.3 Produce an endpoint map

For each endpoint record: - HTTP method/path. - Router prefix and app
registration. - Auth and authorization requirements. - Request/response
models. - Tables touched. - Status transitions. - Tests.

Resolve `/api/v1` concerns by comparing `main.py`, router prefixes,
frontend base URL, endpoint strings and OpenAPI paths. Do not change
prefixes until the actual mismatch is proven.

## 3.4 Baseline

Before edits: - Run backend deterministic tests. - Run frontend
production build. - Record exact results and warnings. - Record
`git status` and uncommitted changes. - Identify migration head. - Do
not discard user changes.

**WP0 exit:** audit note exists; no application files modified.

------------------------------------------------------------------------

# 4. WP1 --- Fix demo workspace/client ID mismatch

**Reported symptom:** `seed_demo.py` and API use different `client_id`
values.

## 4.1 Establish one source of truth

Inspect: - `seed_demo.py` - Backend settings/configuration. -
`DEFAULT_CLIENT_ID` or equivalent. - Client/workspace migrations. - All
repository filters using `client_id`. - Invoice upload/creation. - PO
seed and lookup. - Approval/exception queries.

Choose a canonical strategy consistent with the actual schema.

For the single-workspace demo, if a client FK is required: 1. Resolve a
configured workspace ID in backend configuration. 2. Confirm the
referenced workspace row exists. 3. Seed/find the same workspace
idempotently. 4. Use the same resolved workspace for invoices, POs,
processing runs, approvals and exceptions. 5. Never invent a UUID or
silently fall back to an unrelated client. 6. Never trust a
browser-supplied workspace ID over backend authorization.

If the schema does not require a client FK, do not add one merely for
consistency.

## 4.2 Seed behaviour

Make seed script idempotent: - First run creates/finds required
workspace and demo data. - Subsequent runs do not duplicate. - Does not
overwrite user-created records. - Does not delete existing records. -
Synthetic fixtures are clearly labelled. - Missing required config fails
clearly. - Use stable natural keys or deterministic fixture identifiers
where suitable.

## 4.3 Tests

Test: - Seed and API resolve same workspace. - Repeated seed is
idempotent. - Invoice creation uses canonical workspace. - PO lookup
uses same workspace. - Approval/exception queries scope correctly. -
Missing workspace config fails safely. - Other workspace data is not
returned.

**Acceptance:** no unexplained hardcoded workspace UUID; seed/API match;
backend enforces workspace scope; Phase 1 tests remain green.

------------------------------------------------------------------------

# 5. WP2 --- Fix supplier field/schema mismatch

**Reported symptom:** queries reference `invoices.supplier_name`, but
the column reportedly does not exist.

Do not immediately add a column. Establish the canonical supplier name
source.

## 5.1 Investigation

Inspect: - Invoice table migration. - Invoice header fields/JSON. -
Supplier table, if any. - Intake draft snapshot. - Repository mapping. -
Approval/exception list queries. - Frontend types.

Determine whether supplier name is: - A direct invoice column. - A
related supplier record. - A JSON invoice field. - A linked
intake/extraction field.

Use the existing canonical source. Do not create duplicate supplier-name
storage without a justified schema requirement.

## 5.2 Correct query/API mapping

-   Select only real columns.
-   Use valid relationship joins.
-   Handle absent optional supplier information.
-   Return a stable API response shape.
-   Avoid N+1 queries.
-   Preserve workspace scoping.
-   Do not fabricate supplier names.

A response property named `supplier_name` may be derived from the
canonical source; it need not be a physical DB column.

## 5.3 Tests

Test supplier present, missing supplier, related supplier record, no
related record, approval list, exception list, empty results, workspace
isolation and malformed relationships.

**Acceptance:** no invalid physical-column reference; lists return
correctly; missing supplier name is safe; no schema-related 500.

------------------------------------------------------------------------

# 6. WP3 --- AI-optional, failure-safe processing

**Reported symptom:** processing fails when AI is disabled. Audit points
to `router.py` and `ai_analysis.py`.

## 6.1 Separate stages

Processing must separate: 1. Load invoice and line items. 2. Run
deterministic validation. 3. Persist deterministic results. 4. If AI is
enabled/configured, run AI analysis. 5. Persist successful analysis or
explicit AI-unavailable state. 6. Create appropriate actionable workflow
record. 7. Persist correct invoice/processing status.

Use existing schema and state enums where possible.

## 6.2 Required behaviour

  -----------------------------------------------------------------------
  AI condition                        Expected behaviour
  ----------------------------------- -----------------------------------
  Enabled, provider succeeds          Deterministic checks + AI analysis

  Intentionally disabled              Deterministic checks run; AI
                                      explicitly disabled/not run

  Missing key                         Deterministic checks run; AI
                                      unavailable/config error

  Timeout                             Deterministic results persist; AI
                                      failed/retryable

  Rate limit                          Preserve deterministic results;
                                      retryable error

  Malformed response                  Reject invalid output; no false
                                      success

  Incomplete output                   Mark incomplete/failed safely

  Retry succeeds                      Persist new successful analysis;
                                      preserve prior attempt
  -----------------------------------------------------------------------

Do not fabricate an AI result when disabled. Do not label
deterministic-only processing as AI-complete.

## 6.3 State separation

Inspect existing fields. Keep these concepts separate where schema
supports them: - Invoice workflow status. - Deterministic validation
status. - AI analysis status. - Processing run status.

Do not overload one field.

Conceptual AI states may include `NOT_REQUESTED`, `DISABLED`, `QUEUED`,
`RUNNING`, `SUCCEEDED`, `FAILED`, `RETRYABLE`, but use existing
vocabulary if present and respect DB constraints.

## 6.4 Idempotency and recovery

-   AI failure must not erase deterministic findings.
-   AI failure must not create approval recommendation.
-   Retry must not duplicate invoice.
-   Repeated processing must be idempotent.
-   Processing run outcome must persist.
-   Errors must not contain secrets.
-   UI must distinguish AI disabled, failed, pending and successful.

## 6.5 Tests

AI disabled, missing key, timeout, rate limit, malformed output,
incomplete output, retry success, deterministic failure, repeated
processing, provider error and concurrent processing.

**Acceptance:** deterministic processing works with AI off; AI state is
honest; results survive AI failure; no automatic approval; retry is
persisted and safe.

------------------------------------------------------------------------

# 7. WP4 --- Runtime creation of approvals and exceptions

**Reported symptom:** approval and exception records are not created
during runtime.

## 7.1 Define routing rules before coding

Inspect existing status constraints, approval/exception schema and
business rules.

Use an explicit mapping:

  -----------------------------------------------------------------------
  Processing outcome                  Required behaviour
  ----------------------------------- -----------------------------------
  Deterministic checks pass and       Create/update pending human-review
  analysis complete                   item

  Deterministic actionable issue      Create actionable exception

  AI flags unconfirmed suspicion      Persist AI finding; route to human
                                      review per policy

  AI disabled/provider failure        Preserve deterministic results;
                                      mark AI unavailable; no fabricated
                                      recommendation

  Missing mandatory data              Create actionable
                                      exception/clarification item

  Confirmed duplicate                 Apply existing duplicate policy;
                                      create duplicate exception or block
                                      as specified

  Potential duplicate only            Persist finding for human review;
                                      do not call it confirmed
  -----------------------------------------------------------------------

Do not assume every failed check requires an exception or every invoice
requires an approval. Document the exact rule.

## 7.2 Idempotency

Repeated processing must not create duplicate active
approvals/exceptions.

Use transaction-safe logic and, where appropriate, database uniqueness
constraints. Candidate keys may involve: - Invoice ID. - Workflow item
type. - Active/unresolved state. - Stable finding code/key. - Processing
run ID.

Choose the actual key based on lifecycle semantics. A resolved issue
recurring after resubmission may need a new active exception.

Avoid race-prone check-then-insert logic without a database constraint
or transaction-safe operation.

## 7.3 Transaction integrity

Where practical, create workflow records and update invoice status
atomically.

If current Supabase/PostgREST calls cannot provide required transaction
semantics, consider a database function/RPC only if it fits the
architecture and can be tested.

Handle partial failures: - Run created, workflow record failed. -
Workflow record created, status update failed. - Concurrent
processing. - Reprocessing after correction.

Do not leave an invoice silently stuck or create duplicate active items.

## 7.4 Record requirements

Approval record should link to invoice, workspace if required,
queue/reviewer if supported, status and timestamps. Link analysis/run if
useful and supported.

Exception record should include invoice, stable category/code,
description, severity, evidence/source, state, timestamps, assignment
and resolution details where schema supports them.

Keep confirmed deterministic failures distinct from AI suspicions.

## 7.5 Tests

-   Valid invoice creates pending approval.
-   Missing fields create actionable exception.
-   Invalid GSTIN creates correct finding/exception.
-   Tax mismatch creates actionable exception.
-   Confirmed duplicate follows policy.
-   AI-only suspicion is not labelled confirmed.
-   AI disabled still creates deterministic workflow records.
-   Repeated/concurrent processing creates no duplicate active items.
-   Resubmission updates/reopens workflow correctly.
-   Records use canonical workspace.

**Acceptance:** real processing creates persisted approval/exception
items; queues populate from actual processing; no seed/mock rows are
required; idempotency proven.

------------------------------------------------------------------------

# 8. WP5 --- Fix Copilot authentication

**Reported symptom:** Copilot UI does not send token, causing 401.

Reuse the existing Supabase browser client/session approach. Do not
create a second auth system.

## 8.1 Frontend

-   Obtain current Supabase session.
-   Attach `Authorization: Bearer <access_token>` to protected copilot
    calls.
-   Do not send fabricated actor IDs.
-   Do not hardcode or log tokens.
-   Handle no session and expired session.
-   Use supported Supabase session refresh.
-   Provide sign-in navigation consistent with app.
-   Clear sensitive state on logout.
-   Prefer shared authenticated API helper.

## 8.2 Backend

-   Verify JWT server-side.
-   Derive identity from verified token.
-   Authorize access to each invoice/PO/workspace record.
-   Never trust user/workspace IDs in request body.
-   Return 401 for missing/invalid auth.
-   Return 403 for authenticated but unauthorized access, or a safe
    not-found response where needed to avoid resource enumeration.

## 8.3 Grounding and safety

-   Retrieve only records caller may access.
-   Bound LLM context.
-   Treat invoice/PO content as untrusted data.
-   Do not execute arbitrary SQL.
-   Do not permit approval/rejection actions.
-   Cite invoice IDs and supporting records.
-   State when data is unavailable.

## 8.4 Tests

No token, invalid token, expired token, valid authorized token,
unauthorized record, frontend token attachment, session expiry,
cross-workspace access and prompt injection.

**Acceptance:** signed-in authorized user can use Copilot; backend
remains authority; no token leaks.

------------------------------------------------------------------------

# 9. WP6 --- Secure exception assignment and resolution

**Reported symptom:** assignment/resolution endpoints are
unauthenticated.

## 9.1 Inventory all exception routes

Include list, detail, assign, reassign, resolve, reopen and comments if
present. Classify each as authenticated read, reviewer mutation, admin
mutation or genuinely public (only with explicit justification).

Default invoice/exception data to authenticated access.

## 9.2 Mutation controls

For assignment and resolution: - Require verified Supabase JWT. - Derive
actor from token. - Ignore/reject browser actor ID. - Verify
reviewer/admin role or permission. - Verify workspace access. - Verify
valid exception state. - Verify assignment target is authorized. -
Prevent invalid repeated resolution unless explicitly idempotent. - Use
shared authorization helpers.

## 9.3 Audit

Record verified actor, timestamp, prior/new state, resolution note,
invoice/workflow reference. Do not delete an exception to represent
resolution.

## 9.4 Tests

Unauthenticated -\> 401; invalid token -\> 401; non-reviewer -\> 403;
authorized reviewer -\> success; cross-workspace -\> denied; invalid
assignment target -\> denied; repeated resolution -\> controlled result;
actor spoofing -\> prevented.

**Acceptance:** all exception mutations are authenticated and authorized
server-side.

------------------------------------------------------------------------

# 10. WP7 --- Supabase RLS and Storage security

**Reported symptom:** RLS policies reportedly missing.

This is high risk. Do not blindly enable RLS on all tables. First map
actual access paths.

## 10.1 Access model inventory

For every relevant table determine: - RLS enabled? - Existing
policies? - Frontend direct access? - Backend uses anon key, user JWT or
service-role? - Backend workspace scoping? - Sensitive content? -
Reviewer/admin mutation rights?

## 10.2 Policy principles

-   Enable RLS on exposed sensitive tables as appropriate.
-   Least privilege.
-   Workspace scope enforced server-side and in policies where relevant.
-   Never trust client-supplied `client_id`.
-   No broad `USING (true)` on invoice data.
-   Service-role key backend-only.
-   Authenticated user is not automatically reviewer.
-   Service-role bypasses RLS, so backend authorization remains
    mandatory.
-   Single-workspace demo does not mean public access.

Review actual tables corresponding to: - Invoices. - Intake drafts. -
Invoice line items. - Document metadata. - Processing runs. - AI
analyses. - Approvals. - Exceptions. - Audit events. - Purchase
orders. - PO line items. - Workspace/membership configuration.

Do not invent table names.

## 10.3 Storage

Verify: - `invoices` bucket private. - Anonymous list/download denied. -
Authorized reviewer can access permitted document. - Signed URLs expire
reasonably. - Paths are workspace-scoped where required. -
Ownership/workspace linkage checked. - No public policy added just to
make PDF preview work.

## 10.4 Migration safeguards

-   Add a new migration; do not edit an already-applied migration.
-   Use explicit policy names.
-   Review prior policies before replacement.
-   Document rollback/recovery.
-   Do not apply remotely.
-   Test anonymous, authenticated non-reviewer, reviewer and backend
    contexts.

**Acceptance:** RLS posture documented; unauthorized access denied;
valid flows work; storage private; service-role backend-only.

------------------------------------------------------------------------

# 11. WP8 --- Environment, API routing and request validation

## 11.1 Example environment files

Inspect: - `apps/api/.env.example` - `apps/web/.env.local.example` -
Actual env loading. - `.gitignore`. - Git history if relevant.

Rules: - Example files use placeholders, not project-specific live
values. - Frontend may use only browser-safe Supabase URL and
anon/publishable key. - Service-role key never in frontend. - Do not
print current secrets. - Do not rotate credentials automatically. - If a
credential was committed, report that deleting it from the latest file
does not remove it from Git history; recommend rotation through provider
controls if it was genuinely exposed.

Example placeholders (use actual variable names already supported by
code):

``` env
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_OR_PUBLISHABLE_KEY
```

Do not rename variables without updating every consumer and
documentation.

## 11.2 API paths

Compare app registration, router prefixes, frontend base URL and path
strings. Establish one convention. Do not double-prefix `/api/v1`.

Add tests for exact paths used by frontend and verify through OpenAPI.

## 11.3 Request body validation

For every mutation: - Define Pydantic request model. - Mark required
fields. - Use defaults only when semantically correct. -
Missing/malformed body -\> controlled 400/422. - Never dereference
`None`. - Validate UUIDs, enums, lengths and allowed values. - Do not
trust browser actor/workspace IDs. - Do not make all fields optional
just to avoid 422.

## 11.4 Error handling

Use correct status codes. Do not return raw DB errors or secrets. Log
useful non-sensitive context. Distinguish validation, auth,
authorization, not-found, conflict, provider and internal errors.

**Acceptance:** no live project-specific credentials in examples; paths
match; invalid payloads return controlled 4xx; no known mutation route
crashes on absent body.

------------------------------------------------------------------------

# 12. WP9 --- Frontend wiring

Do not redesign the product. Fix broken workflows and preserve existing
visual language.

## 12.1 Approvals

Verify: - Correct endpoint and response mapping. - Canonical supplier
display field. - Workspace scope. - Empty/loading/error states. -
Correct invoice navigation. - Persisted AI findings/recommendation
only. - Authenticated actions. - Buttons disabled while request is in
flight. - Successful action refreshes list. - Failed action does not
falsely change UI state.

## 12.2 Exceptions

Verify: - Correct schema/API field mapping. - Supplier display. -
Authenticated assignment and resolution. - No browser-supplied actor. -
Comment validation. - Persisted open/resolved state after refresh. -
Empty/loading/error states. - No placeholder exceptions.

## 12.3 Copilot

Verify: - Current session read. - Bearer token sent. - 401
sign-in/session message. - 403 authorization message. - Loading/provider
failure states. - Invoice references open correct invoice. - Context
bounded. - No fake answers shown as live results.

## 12.4 Processing/dashboard

Verify: - Persisted processing state. - AI disabled/failure not shown as
AI success. - Actual approvals/exceptions appear after processing. -
Dashboard counts match backend/database. - Filters do not hide data
through stale workspace IDs.

## 12.5 All routes

Visit all existing routes: - No unexpected 404. - No runtime errors. -
No repeated failed requests. - No dead buttons. - No incorrect links. -
No sensitive browser-console output.

**Acceptance:** every visible action works or is clearly disabled with
explanation; pages use real persisted data; refresh preserves state.

------------------------------------------------------------------------

# 13. WP10 --- Isolated integration testing

The previous audit deferred live Supabase because the target was not
confirmed as a test environment. Preserve that safeguard.

## 13.1 Environment gate

Before live integration: 1. Confirm project is development/test. 2.
Confirm no production/customer data. 3. Confirm isolated test workspace
and user. 4. Confirm cleanup only targets current test-run records. 5.
Confirm storage cleanup limited to test prefix. 6. Obtain explicit
approval for destructive tests.

If unknown, do not run destructive tests.

## 13.2 Synthetic fixtures

Use synthetic Indian GST invoices and POs: - Unique test invoice
prefix. - INR. - Known taxable value and tax breakdown. - Valid
synthetic GSTIN test values accepted by the implementation. - Matching
PO. - Controlled quantity/price mismatch. - No real supplier or bank
details.

Include: - Valid invoice. - Missing-field invoice. - GST mismatch. - Tax
mismatch. - Duplicate business invoice with different PDF hash. - PO
quantity mismatch. - AI provider failure case.

## 13.3 Separate suites

-   Deterministic tests: no network.
-   Mocked integration: controlled mocks, labelled as mocked.
-   Live OpenRouter: configured credentials, timeout, no key logging.
-   Live Supabase: isolated test workspace only.
-   Browser E2E: test account and synthetic fixtures.

If Playwright is absent, assess existing test tooling first. Add it only
with clear justification and minimal setup.

## 13.4 Core scenarios

**A --- Normal invoice:** upload, extract, edit/save, submit, validate,
AI if enabled, create approval, sign in, approve, verify
status/audit/dashboard.

**B --- Tax mismatch:** upload, detect mismatch, persist
finding/exception, AI explain if available, ensure no auto-approval,
human resolution and history.

**C --- Duplicate business invoice:** upload original and different PDF
representing same supplier GSTIN + invoice number; verify different file
hash but duplicate business key; prevent accidental duplicate approval.

**D --- AI disabled:** submit; deterministic checks run; AI marked
disabled; deterministic workflow record created; no fake AI
recommendation.

**E --- Provider outage:** simulate timeout; deterministic results
persist; AI failed/retryable; no approval from failure; retry succeeds;
history consistent.

**F --- Copilot:** sign in; ask about known invoice; verify token,
authorization, grounded answer and cross-workspace denial.

**G --- Exception assignment/resolution:** no token -\> 401;
non-reviewer -\> 403; authorized reviewer assigns/resolves; verify
actor/timestamp.

**H --- PO matching:** import synthetic PO; exact match; quantity
mismatch; AI explains but does not overwrite values; human decides.

------------------------------------------------------------------------

# 14. WP11 --- Regression and final report

## 14.1 Quality gates

Backend: - Full deterministic pytest suite. - Focused tests for every
fixed defect. - Auth/authorization. - Repository/query tests. -
Processing idempotency. - Workflow transitions. - AI provider failure.

Frontend: - Production build. - TypeScript check if separately
configured. - Existing tests. - Approval, exception and copilot route
tests. - Browser E2E if available.

Database: - Migration syntax reviewed. - Migration order. -
Columns/constraints. - RLS policies. - Workspace foreign keys. - Private
storage access.

Integrations: - OpenRouter live result separately reported. - Supabase
live result separately reported. - Mocked tests clearly labelled. -
Never claim live success from mocks.

## 14.2 Regression

After each work package: - Run focused tests. - Run related existing
tests. - Review `git diff`. - Check unintended schema changes. - Check
no secrets added. - Check no previously working feature removed.

After all work: - Full backend suite. - Frontend production build. -
Safe E2E suite. - Compare against baseline. - Do not silently
skip/deselect failures.

## 14.3 Final report

Create `docs/QA_REMEDIATION_REPORT.md` containing: 1. Executive summary.
2. Original defect and severity. 3. Root cause established from
code/schema. 4. Fix implemented. 5. Files changed. 6. Migrations and
purpose. 7. Tests added. 8. Exact commands. 9. Actual results. 10. Live
integration results. 11. Remaining defects. 12. Blocked tests and
reasons. 13. Manual Supabase steps. 14. Rollback/recovery notes. 15.
Residual security risks.

Use:

  -----------------------------------------------------------------------------------------------
  ID             Finding                Severity       Status                      Evidence
  -------------- ---------------------- -------------- --------------------------- --------------
  D-01           AI-disabled processing Critical       PASS/PARTIAL/FAIL/BLOCKED   Test reference
                 failure                                                           

  D-02           Runtime                Critical       ...                         ...
                 approvals/exceptions                                              
                 missing                                                           

  D-03           Invalid supplier field Critical       ...                         ...
                 query                                                             

  D-04           Copilot missing auth   High           ...                         ...
                 token                                                             

  D-05           Exception mutation     High           ...                         ...
                 unauthenticated                                                   

  D-06           RLS policies missing   High           ...                         ...

  D-07           Seed/API workspace     High           ...                         ...
                 mismatch                                                          

  D-08           Live credentials in    Medium         ...                         ...
                 example file                                                      

  D-09           API route prefix       Medium         ...                         ...
                 inconsistency                                                     

  D-10           Missing request-body   Medium         ...                         ...
                 validation                                                        
  -----------------------------------------------------------------------------------------------

Allowed statuses: PASS, PARTIAL, FAIL, BLOCKED, NOT APPLICABLE.

A defect is PASS only after a test demonstrates expected behaviour, not
merely because code changed.

------------------------------------------------------------------------

# 15. Exact Cursor checkpoints

Do not combine the whole remediation into one implementation pass.

## Checkpoint 1 --- Read-only audit

-   Reconfirm all ten defects.
-   Produce schema, endpoint, workspace and auth maps.
-   Report uncommitted changes and baseline tests.
-   Do not edit code or migrations.

Stop and report.

## Checkpoint 2 --- Data/query correctness

Implement WP1 and WP2. Run focused tests. Stop and report.

## Checkpoint 3 --- Processing/workflow

Implement WP3 and WP4. Run focused tests. Stop and report.

## Checkpoint 4 --- Authentication

Implement WP5 and WP6. Run focused tests. Stop and report.

## Checkpoint 5 --- RLS/configuration

Implement WP7 and WP8. Do not apply remote migrations. Provide exact SQL
and manual steps. Stop and report.

## Checkpoint 6 --- Frontend

Implement WP9. Run build and focused frontend tests. Stop and report.

## Checkpoint 7 --- Isolated integration

Only after confirming safe test Supabase environment and user
authorization. Execute WP10. Stop and report.

## Checkpoint 8 --- Final verification

Execute WP11 and generate final report.

------------------------------------------------------------------------

# 16. Non-negotiable product invariants

1.  Digital PDF upload creates a persisted invoice/document link.
2.  Unknown extracted values remain NULL.
3.  Review edits survive refresh.
4.  Submission persists a valid status transition.
5.  Deterministic validation runs when AI is disabled.
6.  AI failure never becomes AI success.
7.  AI cannot hide deterministic failures.
8.  Processing creates real actionable approval/exception records.
9.  Repeated processing creates no duplicate active workflow records.
10. Approval/exception lists query actual schema fields.
11. Copilot uses authenticated, authorized access.
12. Exception assignment/resolution require authorization.
13. RLS does not expose invoice data to anonymous/unrelated users.
14. Seed and API use consistent workspace resolution.
15. Reviewer identity comes from verified JWT.
16. Only authorized human can approve/reject.
17. Every final decision is persisted and auditable.
18. Dashboard metrics reflect persisted records.
19. PO matching uses real persisted PO/invoice data.
20. Copilot is grounded in records caller may access.
21. No secrets in frontend code, example files or logs.
22. Existing working features remain functional.

------------------------------------------------------------------------

# 17. Start here --- exact first instruction

**Begin with Checkpoint 1 only. Do not modify application code.**

Return: - Confirmed versus unconfirmed defects. - Relevant file paths. -
Actual database columns and relationships. - Existing API routes and
prefixes. - Auth and RLS posture. - Current workspace resolution. -
Baseline backend test output. - Frontend build result. - Uncommitted Git
changes. - Ambiguities requiring decisions before implementation.

Wait for explicit approval before Checkpoint 2.

The objective is to fix root causes safely, not to maximise changed
files or produce a superficially successful test report.
