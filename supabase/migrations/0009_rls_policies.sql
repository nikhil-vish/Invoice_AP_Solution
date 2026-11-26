-- -----------------------------------------------------------
-- WP7: RLS policies for single-workspace demo
-- RLS was enabled (rule of 0001:269-288) but zero policies exist.
-- These policies enforce workspace scope using the demo client ID
-- established in migration 0005 and seed_demo.py.  The backend uses
-- the service-role key (bypasses RLS), so adding these policies
-- does not affect any existing code path.  They protect direct
-- anon-key / browser access and document the intended access model.
-- -----------------------------------------------------------

-- Helper: demo client ID (the one seeded by migration 0005).
create or replace function public.demo_client_id()
returns uuid language sql stable
as \$\$ select '11111111-1111-4111-8111-111111111111'::uuid \$\$;

-- Only create/adjust policies where a client_id or invoice_id
-- column exists and the table is not already RLS-forced by backend.
-- The rule "no USING (true) on invoice data" is honoured: policies
-- reference the demo client explicitly rather than a blanket true.

-- invoices --------------------------------------------------------
alter table public.invoices enable row level security;
create policy "invoices_select_for_demo" on public.invoices
    for select using ( client_id = public.demo_client_id() );
create policy "invoices_insert_for_demo" on public.invoices
    for insert with check ( client_id = public.demo_client_id() );
-- update/delete restricted to backend only via service-role; policy
-- here documents intent for any direct access.
create policy "invoices_update_for_demo" on public.invoices
    for update using ( client_id = public.demo_client_id() );
create policy "invoices_delete_for_demo" on public.invoices
    for delete using ( client_id = public.demo_client_id() );

-- client_entities -------------------------------------------------
alter table public.client_entities enable row level security;
create policy "client_entities_select_for_demo" on public.client_entities
    for select using ( client_id = public.demo_client_id() );
create policy "client_entities_insert_for_demo" on public.client_entities
    for insert with check ( client_id = public.demo_client_id() );

-- suppliers -------------------------------------------------------
alter table public.suppliers enable row level security;
create policy "suppliers_select_for_demo" on public.suppliers
    for select using ( client_id = public.demo_client_id() );
create policy "suppliers_insert_for_demo" on public.suppliers
    for insert with check ( client_id = public.demo_client_id() );

-- invoice_items -------------------------------------------------
alter table public.invoice_items enable row level security;
-- linked via invoice_id; enforce workspace through the parent invoice.
create policy "invoice_items_select_for_demo" on public.invoice_items
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "invoice_items_insert_for_demo" on public.invoice_items
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- invoice_documents -----------------------------------------------
alter table public.invoice_documents enable row level security;
create policy "invoice_documents_select_for_demo" on public.invoice_documents
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "invoice_documents_insert_for_demo" on public.invoice_documents
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- processing_runs -------------------------------------------------
alter table public.processing_runs enable row level security;
create policy "processing_runs_select_for_demo" on public.processing_runs
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "processing_runs_insert_for_demo" on public.processing_runs
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- validation_results ----------------------------------------------
alter table public.validation_results enable row level security;
create policy "validation_results_select_for_demo" on public.validation_results
    for select using ( exists (
        select 1 from public.processing_runs pr
        join public.invoices i on i.id = pr.invoice_id
        where i.client_id = public.demo_client_id()
    ) );
create policy "validation_results_insert_for_demo" on public.validation_results
    for insert with check ( exists (
        select 1 from public.processing_runs pr
        join public.invoices i on i.id = pr.invoice_id
        where i.client_id = public.demo_client_id()
    ) );

-- exceptions ----------------------------------------------------
alter table public.exceptions enable row level security;
create policy "exceptions_select_for_demo" on public.exceptions
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "exceptions_insert_for_demo" on public.exceptions
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- approvals -------------------------------------------------------
alter table public.approvals enable row level security;
create policy "approvals_select_for_demo" on public.approvals
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "approvals_insert_for_demo" on public.approvals
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- audit_logs ------------------------------------------------------
alter table public.audit_logs enable row level security;
create policy "audit_logs_select_for_demo" on public.audit_logs
    for select using ( client_id = public.demo_client_id() );

-- invoice_ai_analyses -------------------------------------------
alter table public.invoice_ai_analyses enable row level security;
create policy "invoice_ai_analyses_select_for_demo" on public.invoice_ai_analyses
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "invoice_ai_analyses_insert_for_demo" on public.invoice_ai_analyses
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- invoice_lifecycle_events --------------------------------------
alter table public.invoice_lifecycle_events enable row level security;
create policy "invoice_lifecycle_events_select_for_demo" on public.invoice_lifecycle_events
    for select using ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );
create policy "invoice_lifecycle_events_insert_for_demo" on public.invoice_lifecycle_events
    for insert with check ( exists (
        select 1 from public.invoices i
        where i.id = invoice_id and i.client_id = public.demo_client_id()
    ) );

-- purchase_orders ------------------------------------------------
alter table public.purchase_orders enable row level security;
create policy "purchase_orders_select_for_demo" on public.purchase_orders
    for select using ( client_entity_id in (
     
