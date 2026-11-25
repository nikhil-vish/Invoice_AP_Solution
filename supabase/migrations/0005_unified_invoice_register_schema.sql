-- Phase 1, part 2: run after 0004 has committed.
-- The IDs are legitimate records seeded here; the API resolves them by name.

insert into public.clients (id, legal_name, display_name, status)
values (
  '11111111-1111-4111-8111-111111111111',
  'Invoice Intelligence Demo Workspace',
  'Invoice Intelligence Demo Workspace',
  'ACTIVE'
)
on conflict (id) do update
set legal_name = excluded.legal_name,
    display_name = excluded.display_name,
    status = 'ACTIVE';

insert into public.client_entities (id, client_id, legal_name, gstin, is_active)
values (
  '22222222-2222-4222-8222-222222222222',
  '11111111-1111-4111-8111-111111111111',
  'Invoice Intelligence Demo Workspace',
  null,
  true
)
on conflict (id) do update
set client_id = excluded.client_id,
    legal_name = excluded.legal_name,
    is_active = true;

alter table public.invoices
  add column if not exists supplier_legal_name text,
  add column if not exists supplier_gstin text,
  add column if not exists supplier_address text,
  add column if not exists due_date date,
  add column if not exists buyer_legal_name text,
  add column if not exists buyer_gstin text,
  add column if not exists po_number text,
  add column if not exists total_tax numeric(18,2),
  add column if not exists current_stage text not null default 'REVIEW',
  add column if not exists validation_status public.validation_status;

alter table public.invoices
  alter column processing_status set default 'DRAFT';

create index if not exists invoices_demo_register_idx
  on public.invoices (client_id, processing_status, created_at desc);

create index if not exists invoices_supplier_invoice_idx
  on public.invoices (supplier_gstin, invoice_number);
