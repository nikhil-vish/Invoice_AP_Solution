-- WP7: Supabase RLS and Storage security for the single-workspace demo.
-- Corrected migration. Safe to re-run: every policy is dropped (by exact name)
-- before it is created, and no unrelated policy is touched.
--
-- Access model (defense in depth; the backend always uses the service-role key
-- which bypasses RLS, so these policies only govern direct anon/authenticated
-- access and never replace backend authorization):
--   * anon          -> no privileges, no policies  => fully denied.
--   * authenticated -> SELECT only, workspace-scoped to the demo client.
--                      No browser INSERT/UPDATE/DELETE on financial records.
--   * service_role  -> unchanged (bypasses RLS); backend remains the writer.
--
-- Canonical workspace: seeded by migration 0005 and resolved by
-- app.invoices.repository.resolve_demo_workspace() using display_name
-- 'Invoice Intelligence Demo Workspace' + status 'ACTIVE'. The function below
-- resolves it dynamically (security definer so it can read RLS-protected
-- public.clients) rather than hardcoding a UUID.

-- ---------------------------------------------------------------------------
-- Canonical demo workspace resolver
-- ---------------------------------------------------------------------------
create or replace function public.demo_client_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select id
  from public.clients
  where display_name = 'Invoice Intelligence Demo Workspace'
    and status = 'ACTIVE'
  order by created_at
  limit 1
$$;

-- ---------------------------------------------------------------------------
-- Read tables: workspace-scoped SELECT for authenticated, none for anon.
-- All writes stay with the backend service role.
-- ---------------------------------------------------------------------------

-- invoices ------------------------------------------------------------
alter table public.invoices enable row level security;
drop policy if exists "invoices_select_for_demo" on public.invoices;
create policy "invoices_select_for_demo" on public.invoices
  for select to authenticated
  using ( client_id = public.demo_client_id() );
revoke all on public.invoices from anon;
revoke insert, update, delete on public.invoices from authenticated;
grant select on public.invoices to authenticated;

-- client_entities -----------------------------------------------------
alter table public.client_entities enable row level security;
drop policy if exists "client_entities_select_for_demo" on public.client_entities;
create policy "client_entities_select_for_demo" on public.client_entities
  for select to authenticated
  using ( client_id = public.demo_client_id() );
revoke all on public.client_entities from anon;
revoke insert, update, delete on public.client_entities from authenticated;
grant select on public.client_entities to authenticated;

-- suppliers -----------------------------------------------------------
alter table public.suppliers enable row level security;
drop policy if exists "suppliers_select_for_demo" on public.suppliers;
create policy "suppliers_select_for_demo" on public.suppliers
  for select to authenticated
  using ( client_id = public.demo_client_id() );
revoke all on public.suppliers from anon;
revoke insert, update, delete on public.suppliers from authenticated;
grant select on public.suppliers to authenticated;

-- invoice_items -------------------------------------------------------
alter table public.invoice_items enable row level security;
drop policy if exists "invoice_items_select_for_demo" on public.invoice_items;
create policy "invoice_items_select_for_demo" on public.invoice_items
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = invoice_items.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.invoice_items from anon;
revoke insert, update, delete on public.invoice_items from authenticated;
grant select on public.invoice_items to authenticated;

-- invoice_documents ---------------------------------------------------
alter table public.invoice_documents enable row level security;
drop policy if exists "invoice_documents_select_for_demo" on public.invoice_documents;
create policy "invoice_documents_select_for_demo" on public.invoice_documents
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = invoice_documents.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.invoice_documents from anon;
revoke insert, update, delete on public.invoice_documents from authenticated;
grant select on public.invoice_documents to authenticated;

-- processing_runs -----------------------------------------------------
alter table public.processing_runs enable row level security;
drop policy if exists "processing_runs_select_for_demo" on public.processing_runs;
create policy "processing_runs_select_for_demo" on public.processing_runs
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = processing_runs.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.processing_runs from anon;
revoke insert, update, delete on public.processing_runs from authenticated;
grant select on public.processing_runs to authenticated;

-- validation_results --------------------------------------------------
-- Correlated to the current row's processing_run (fixes the prior
-- uncorrelated subquery that exposed every result in the workspace).
alter table public.validation_results enable row level security;
drop policy if exists "validation_results_select_for_demo" on public.validation_results;
create policy "validation_results_select_for_demo" on public.validation_results
  for select to authenticated
  using ( exists (
    select 1
    from public.processing_runs pr
    join public.invoices i on i.id = pr.invoice_id
    where pr.id = validation_results.processing_run_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.validation_results from anon;
revoke insert, update, delete on public.validation_results from authenticated;
grant select on public.validation_results to authenticated;

-- exceptions ----------------------------------------------------------
alter table public.exceptions enable row level security;
drop policy if exists "exceptions_select_for_demo" on public.exceptions;
create policy "exceptions_select_for_demo" on public.exceptions
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = exceptions.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.exceptions from anon;
revoke insert, update, delete on public.exceptions from authenticated;
grant select on public.exceptions to authenticated;

-- approvals -----------------------------------------------------------
alter table public.approvals enable row level security;
drop policy if exists "approvals_select_for_demo" on public.approvals;
create policy "approvals_select_for_demo" on public.approvals
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = approvals.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.approvals from anon;
revoke insert, update, delete on public.approvals from authenticated;
grant select on public.approvals to authenticated;

-- audit_logs ----------------------------------------------------------
alter table public.audit_logs enable row level security;
drop policy if exists "audit_logs_select_for_demo" on public.audit_logs;
create policy "audit_logs_select_for_demo" on public.audit_logs
  for select to authenticated
  using ( client_id = public.demo_client_id() );
revoke all on public.audit_logs from anon;
revoke insert, update, delete on public.audit_logs from authenticated;
grant select on public.audit_logs to authenticated;

-- invoice_ai_analyses -------------------------------------------------
alter table public.invoice_ai_analyses enable row level security;
drop policy if exists "invoice_ai_analyses_select_for_demo" on public.invoice_ai_analyses;
create policy "invoice_ai_analyses_select_for_demo" on public.invoice_ai_analyses
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = invoice_ai_analyses.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.invoice_ai_analyses from anon;
revoke insert, update, delete on public.invoice_ai_analyses from authenticated;
grant select on public.invoice_ai_analyses to authenticated;

-- invoice_lifecycle_events -------------------------------------------
alter table public.invoice_lifecycle_events enable row level security;
drop policy if exists "invoice_lifecycle_events_select_for_demo" on public.invoice_lifecycle_events;
create policy "invoice_lifecycle_events_select_for_demo" on public.invoice_lifecycle_events
  for select to authenticated
  using ( exists (
    select 1 from public.invoices i
    where i.id = invoice_lifecycle_events.invoice_id
      and i.client_id = public.demo_client_id()
  ) );
revoke all on public.invoice_lifecycle_events from anon;
revoke insert, update, delete on public.invoice_lifecycle_events from authenticated;
grant select on public.invoice_lifecycle_events to authenticated;

-- purchase_orders -----------------------------------------------------
alter table public.purchase_orders enable row level security;
drop policy if exists "purchase_orders_select_for_demo" on public.purchase_orders;
create policy "purchase_orders_select_for_demo" on public.purchase_orders
  for select to authenticated
  using ( exists (
    select 1 from public.client_entities ce
    where ce.id = purchase_orders.client_entity_id
      and ce.client_id = public.demo_client_id()
  ) );
revoke all on public.purchase_orders from anon;
revoke insert, update, delete on public.purchase_orders from authenticated;
grant select on public.purchase_orders to authenticated;

-- purchase_order_items ------------------------------------------------
alter table public.purchase_order_items enable row level security;
drop policy if exists "purchase_order_items_select_for_demo" on public.purchase_order_items;
create policy "purchase_order_items_select_for_demo" on public.purchase_order_items
  for select to authenticated
  using ( exists (
    select 1
    from public.purchase_orders po
    join public.client_entities ce on ce.id = po.client_entity_id
    where po.id = purchase_order_items.purchase_order_id
      and ce.client_id = public.demo_client_id()
  ) );
revoke all on public.purchase_order_items from anon;
revoke insert, update, delete on public.purchase_order_items from authenticated;
grant select on public.purchase_order_items to authenticated;

-- ---------------------------------------------------------------------------
-- Service-role-only tables: RLS enabled, NO browser policy, no browser grants.
-- These hold intake drafts (raw invoice text), bank details, GRN/SES,
-- contracts, budgets and the client registry. Only the backend service role
-- (RLS bypass) may touch them.
-- ---------------------------------------------------------------------------
revoke all on public.clients from anon, authenticated;
revoke all on public.supplier_bank_accounts from anon, authenticated;
revoke all on public.goods_receipts from anon, authenticated;
revoke all on public.goods_receipt_items from anon, authenticated;
revoke all on public.service_entries from anon, authenticated;
revoke all on public.contracts from anon, authenticated;
revoke all on public.budgets from anon, authenticated;
revoke all on public.invoice_intake_drafts from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Private 'invoices' Storage bucket: read-only for authenticated, denied to
-- anon. Uploads/downloads are performed by the backend service role. No
-- browser INSERT/UPDATE/DELETE policies are created. If the SQL editor lacks
-- privileges on storage.objects, create the equivalent policy in the Storage
-- dashboard (bucket 'invoices', SELECT, authenticated).
-- ---------------------------------------------------------------------------
drop policy if exists "invoices_bucket_authenticated_select" on storage.objects;
create policy "invoices_bucket_authenticated_select" on storage.objects
  for select to authenticated
  using ( bucket_id = 'invoices' );

-- ---------------------------------------------------------------------------
-- Manual verification (run each separately; expected: 1 row / 0 rows)
-- ---------------------------------------------------------------------------
-- select public.demo_client_id();                    -- one demo uuid
-- select tablename, policyname, cmd, roles
--   from pg_policies where schemaname = 'public' order by tablename, policyname;
-- select has_table_privilege('anon', 'public.invoices', 'select');        -- false
-- select has_table_privilege('authenticated', 'public.invoices', 'select');-- true
-- select has_table_privilege('authenticated', 'public.invoices', 'delete');-- false