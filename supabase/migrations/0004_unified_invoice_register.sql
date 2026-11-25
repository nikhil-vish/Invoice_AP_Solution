-- Phase 1, part 1: PostgreSQL does not permit a new enum value to be used
-- until this transaction has committed. Apply this migration before 0005.

alter type public.invoice_processing_status add value if not exists 'DRAFT';
alter type public.invoice_processing_status add value if not exists 'QUEUED';
