-- Invoice Intelligence Workbench: initial relational schema.
-- Apply in Supabase SQL Editor. RLS is enabled; policies should be added with auth roles
-- before exposing tenant data to browser clients.

create extension if not exists pgcrypto;

create type public.invoice_procurement_type as enum ('PO', 'NON_PO', 'UNKNOWN');
create type public.invoice_processing_status as enum ('RECEIVED','EXTRACTING','VALIDATING','MATCHING','TAX_CHECK','DECISION_READY','ON_HOLD','APPROVAL_PENDING','APPROVED','REJECTED','FAILED');
create type public.validation_status as enum ('PASSED','FAILED','WARNING','SKIPPED','NEEDS_REVIEW');
create type public.approval_status as enum ('PENDING','APPROVED','REJECTED','REASSIGNED','CANCELLED');

create table public.clients (
  id uuid primary key default gen_random_uuid(),
  legal_name text not null,
  display_name text,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','INACTIVE','ONBOARDING')),
  created_at timestamptz not null default now()
);

create table public.client_entities (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients(id),
  legal_name text not null,
  gstin text,
  registered_email_domains text[] not null default '{}',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (client_id, gstin)
);

create table public.suppliers (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients(id),
  legal_name text not null,
  trade_name text,
  gstin text,
  vendor_code text,
  status text not null default 'PENDING' check (status in ('PENDING','ACTIVE','BLOCKED','INACTIVE')),
  aliases text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (client_id, vendor_code)
);

create table public.supplier_bank_accounts (
  id uuid primary key default gen_random_uuid(),
  supplier_id uuid not null references public.suppliers(id),
  account_holder_name text not null,
  account_number_last4 text,
  ifsc_masked text,
  verification_status text not null default 'UNVERIFIED' check (verification_status in ('UNVERIFIED','VERIFIED','REJECTED')),
  verified_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.purchase_orders (
  id uuid primary key default gen_random_uuid(),
  client_entity_id uuid not null references public.client_entities(id),
  supplier_id uuid not null references public.suppliers(id),
  po_number text not null,
  currency char(3) not null default 'INR',
  total_before_tax numeric(18,2),
  tax_amount numeric(18,2),
  total_amount numeric(18,2) not null,
  status text not null default 'DRAFT' check (status in ('DRAFT','APPROVED','CLOSED','CANCELLED')),
  valid_from date,
  valid_to date,
  created_at timestamptz not null default now(),
  unique (client_entity_id, po_number)
);

create table public.purchase_order_items (
  id uuid primary key default gen_random_uuid(),
  purchase_order_id uuid not null references public.purchase_orders(id) on delete cascade,
  line_number integer not null,
  item_code text,
  description text not null,
  quantity numeric(18,4),
  unit_of_measure text,
  unit_price numeric(18,4),
  taxable_value numeric(18,2),
  gst_rate numeric(6,3),
  created_at timestamptz not null default now(),
  unique (purchase_order_id, line_number)
);

create table public.goods_receipts (
  id uuid primary key default gen_random_uuid(),
  purchase_order_id uuid not null references public.purchase_orders(id),
  grn_number text not null,
  receipt_date date not null,
  status text not null default 'PENDING' check (status in ('PENDING','ACCEPTED','PARTIALLY_ACCEPTED','REJECTED')),
  created_at timestamptz not null default now(),
  unique (purchase_order_id, grn_number)
);

create table public.goods_receipt_items (
  id uuid primary key default gen_random_uuid(),
  goods_receipt_id uuid not null references public.goods_receipts(id) on delete cascade,
  purchase_order_item_id uuid not null references public.purchase_order_items(id),
  received_quantity numeric(18,4) not null default 0,
  accepted_quantity numeric(18,4) not null default 0,
  rejected_quantity numeric(18,4) not null default 0
);

create table public.service_entries (
  id uuid primary key default gen_random_uuid(),
  purchase_order_id uuid references public.purchase_orders(id),
  client_entity_id uuid not null references public.client_entities(id),
  supplier_id uuid not null references public.suppliers(id),
  entry_number text not null,
  service_period_start date,
  service_period_end date,
  accepted_amount numeric(18,2) not null default 0,
  status text not null default 'PENDING' check (status in ('PENDING','APPROVED','PARTIALLY_APPROVED','REJECTED')),
  created_at timestamptz not null default now()
);

create table public.contracts (
  id uuid primary key default gen_random_uuid(),
  client_entity_id uuid not null references public.client_entities(id),
  supplier_id uuid not null references public.suppliers(id),
  contract_reference text not null,
  category text,
  valid_from date,
  valid_to date,
  approved_amount numeric(18,2),
  currency char(3) not null default 'INR',
  status text not null default 'DRAFT' check (status in ('DRAFT','APPROVED','EXPIRED','CANCELLED')),
  created_at timestamptz not null default now()
);

create table public.budgets (
  id uuid primary key default gen_random_uuid(),
  client_entity_id uuid not null references public.client_entities(id),
  department text not null,
  cost_centre text,
  category text,
  period_start date not null,
  period_end date not null,
  budget_amount numeric(18,2) not null,
  currency char(3) not null default 'INR',
  created_at timestamptz not null default now()
);

create table public.invoices (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients(id),
  client_entity_id uuid not null references public.client_entities(id),
  supplier_id uuid references public.suppliers(id),
  invoice_number text,
  invoice_date date,
  currency char(3) not null default 'INR',
  procurement_type public.invoice_procurement_type not null default 'UNKNOWN',
  purchase_order_id uuid references public.purchase_orders(id),
  contract_id uuid references public.contracts(id),
  taxable_value numeric(18,2),
  cgst_amount numeric(18,2) not null default 0,
  sgst_amount numeric(18,2) not null default 0,
  igst_amount numeric(18,2) not null default 0,
  cess_amount numeric(18,2) not null default 0,
  other_charges numeric(18,2) not null default 0,
  discount_amount numeric(18,2) not null default 0,
  total_amount numeric(18,2),
  processing_status public.invoice_processing_status not null default 'RECEIVED',
  approval_status public.approval_status not null default 'PENDING',
  source_email_message_id text,
  source_file_sha256 text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index invoices_client_status_idx on public.invoices(client_id, processing_status);
create index invoices_supplier_number_idx on public.invoices(supplier_id, invoice_number);
create index invoices_po_idx on public.invoices(purchase_order_id);

create table public.invoice_items (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id) on delete cascade,
  line_number integer not null,
  description text,
  item_code text,
  hsn_sac text,
  quantity numeric(18,4),
  unit_of_measure text,
  unit_price numeric(18,4),
  taxable_value numeric(18,2),
  gst_rate numeric(6,3),
  cgst_amount numeric(18,2) not null default 0,
  sgst_amount numeric(18,2) not null default 0,
  igst_amount numeric(18,2) not null default 0,
  total_amount numeric(18,2),
  unique (invoice_id, line_number)
);

create table public.invoice_documents (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id) on delete cascade,
  storage_path text not null,
  original_filename text not null,
  mime_type text not null,
  sha256 text not null,
  document_type text,
  extraction_method text,
  created_at timestamptz not null default now()
);

create table public.processing_runs (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id),
  run_number integer not null,
  status text not null default 'QUEUED' check (status in ('QUEUED','RUNNING','COMPLETED','FAILED','WAITING')),
  started_at timestamptz,
  completed_at timestamptz,
  triggered_by text not null default 'MANUAL_UPLOAD',
  idempotency_key text unique,
  summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (invoice_id, run_number)
);

create table public.validation_results (
  id uuid primary key default gen_random_uuid(),
  processing_run_id uuid not null references public.processing_runs(id) on delete cascade,
  stage text not null,
  rule_code text not null,
  status public.validation_status not null,
  message text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.exceptions (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id),
  processing_run_id uuid references public.processing_runs(id),
  exception_code text not null,
  severity text not null default 'MEDIUM' check (severity in ('LOW','MEDIUM','HIGH','CRITICAL')),
  owner_team text,
  status text not null default 'OPEN' check (status in ('OPEN','AWAITING_RESPONSE','IN_REVIEW','RESOLVED','ESCALATED','CLOSED')),
  description text not null,
  resolution jsonb,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table public.approvals (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id),
  approver_user_id uuid,
  approval_level integer not null default 1,
  status public.approval_status not null default 'PENDING',
  decision_comment text,
  assigned_at timestamptz not null default now(),
  decided_at timestamptz
);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references public.clients(id),
  invoice_id uuid references public.invoices(id),
  actor_type text not null,
  actor_id text,
  action text not null,
  before_state jsonb,
  after_state jsonb,
  created_at timestamptz not null default now()
);

-- Enable RLS on tenant-bearing tables. Add tenant-scoped policies before browser access.
alter table public.clients enable row level security;
alter table public.client_entities enable row level security;
alter table public.suppliers enable row level security;
alter table public.supplier_bank_accounts enable row level security;
alter table public.purchase_orders enable row level security;
alter table public.purchase_order_items enable row level security;
alter table public.goods_receipts enable row level security;
alter table public.goods_receipt_items enable row level security;
alter table public.service_entries enable row level security;
alter table public.contracts enable row level security;
alter table public.budgets enable row level security;
alter table public.invoices enable row level security;
alter table public.invoice_items enable row level security;
alter table public.invoice_documents enable row level security;
alter table public.processing_runs enable row level security;
alter table public.validation_results enable row level security;
alter table public.exceptions enable row level security;
alter table public.approvals enable row level security;
alter table public.audit_logs enable row level security;
