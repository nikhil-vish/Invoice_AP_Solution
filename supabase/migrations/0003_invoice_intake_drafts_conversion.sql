
-- Invoice Intelligence Workbench: draft-to-invoice conversion tracking.
-- Adds fields to invoice_intake_drafts to track which drafts have been
-- converted into business invoice records, enabling idempotent conversion.

alter table public.invoice_intake_drafts
  add column if not exists converted_invoice_id uuid
    references public.invoices(id),
  add column if not exists conversion_status text not null default 'PENDING'
    check (conversion_status in ('PENDING', 'CONVERTED', 'FAILED')),
  add column if not exists converted_at timestamptz;

create index if not exists invoice_intake_drafts_converted_invoice_idx
  on public.invoice_intake_drafts(converted_invoice_id)
  where converted_invoice_id is not null;

create unique index if not exists invoice_intake_drafts_converted_invoice_unique
  on public.invoice_intake_drafts(converted_invoice_id)
  where converted_invoice_id is not null;

alter table public.invoice_intake_drafts
  add constraint if not exists invoice_intake_drafts_conversion_status_check
    check (conversion_status in ('PENDING', 'CONVERTED', 'FAILED'));
