-- Commit enum values before code or later migrations use them.
alter type public.invoice_processing_status add value if not exists 'PROCESSING';
alter type public.invoice_processing_status add value if not exists 'PENDING_APPROVAL';
