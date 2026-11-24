
-- Invoice Intelligence Workbench: intake drafts for pre-identification storage.

create table public.invoice_intake_drafts (
  id uuid primary key default gen_random_uuid(),
  original_filename text not null,
  storage_path text not null,
  mime_type text not null,
  sha256 text not null,
  file_size_bytes bigint not null,
  extracted_data jsonb not null default '{}'::jsonb,
  raw_text text,
  extraction_method text not null default 'pymupdf_digital',
  processing_status text not null default 'EXTRACTED'
    check (processing_status in (
      'EXTRACTED',
      'NEEDS_REVIEW',
      'READY_FOR_VALIDATION',
      'FAILED'
    )),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (sha256)
);

create index invoice_intake_drafts_status_idx
  on public.invoice_intake_drafts(processing_status);

alter table public.invoice_intake_drafts enable row level security;
