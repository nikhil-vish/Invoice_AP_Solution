-- Missing extracted amounts must stay null.
-- 0001 defined currency as NOT NULL default 'INR' and the GST amount columns as
-- NOT NULL default 0. Those defaults cannot represent "not present on the PDF"
-- and would store a fabricated zero or INR. Explicit zeros remain valid values.

alter table public.invoices alter column currency drop not null;
alter table public.invoices alter column currency drop default;
alter table public.invoices alter column cgst_amount drop not null;
alter table public.invoices alter column cgst_amount drop default;
alter table public.invoices alter column sgst_amount drop not null;
alter table public.invoices alter column sgst_amount drop default;
alter table public.invoices alter column igst_amount drop not null;
alter table public.invoices alter column igst_amount drop default;
alter table public.invoices alter column cess_amount drop not null;
alter table public.invoices alter column cess_amount drop default;
alter table public.invoices alter column other_charges drop not null;
alter table public.invoices alter column other_charges drop default;
alter table public.invoices alter column discount_amount drop not null;
alter table public.invoices alter column discount_amount drop default;

alter table public.invoice_items alter column cgst_amount drop not null;
alter table public.invoice_items alter column cgst_amount drop default;
alter table public.invoice_items alter column sgst_amount drop not null;
alter table public.invoice_items alter column sgst_amount drop default;
alter table public.invoice_items alter column igst_amount drop not null;
alter table public.invoice_items alter column igst_amount drop default;
