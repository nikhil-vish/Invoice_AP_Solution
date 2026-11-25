create table public.invoice_ai_analyses (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices(id) on delete cascade,
  processing_run_id uuid references public.processing_runs(id) on delete set null,
  attempt_number integer not null,
  status text not null check (status in ('COMPLETED', 'FAILED')),
  recommendation text,
  risk_level text check (risk_level in ('LOW', 'MEDIUM', 'HIGH')),
  confidence_score integer check (confidence_score between 0 and 100),
  executive_summary text,
  findings jsonb not null default '[]'::jsonb,
  validation_results jsonb not null default '[]'::jsonb,
  model_used text,
  provider_error text,
  generated_at timestamptz,
  created_at timestamptz not null default now(),
  unique (invoice_id, attempt_number)
);

create index invoice_ai_analyses_invoice_created_idx
  on public.invoice_ai_analyses(invoice_id, created_at desc);

alter table public.invoice_ai_analyses enable row level security;
