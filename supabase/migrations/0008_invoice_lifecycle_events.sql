-- Phase 3: durable, queryable invoice lifecycle history.
create table public.invoice_lifecycle_events (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id) on delete cascade,
  processing_run_id uuid references public.processing_runs(id) on delete set null,
  from_status invoice_processing_status,
  to_status invoice_processing_status,
  stage text not null,
  event_type text not null,
  reason text,
  actor_id text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index invoice_lifecycle_events_invoice_created_idx
  on public.invoice_lifecycle_events(invoice_id, created_at desc);

alter table public.invoice_lifecycle_events enable row level security;
