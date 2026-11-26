-- A durable submission state makes the review-to-processing handoff visible.
alter type public.invoice_processing_status add value if not exists 'SUBMITTED';
