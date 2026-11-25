
-- Invoice Intelligence Workbench: draft-to-invoice conversion tracking.
-- Adds fields to invoice_intake_drafts to track converted business invoices.

ALTER TABLE public.invoice_intake_drafts
    ADD COLUMN IF NOT EXISTS converted_invoice_id uuid
        REFERENCES public.invoices(id),
    ADD COLUMN IF NOT EXISTS conversion_status text NOT NULL DEFAULT 'PENDING'
        CHECK (conversion_status IN ('PENDING', 'CONVERTED', 'FAILED')),
    ADD COLUMN IF NOT EXISTS converted_at timestamptz;

-- Index for looking up converted invoices.
CREATE INDEX IF NOT EXISTS invoice_intake_drafts_converted_invoice_idx
    ON public.invoice_intake_drafts(converted_invoice_id)
    WHERE converted_invoice_id IS NOT NULL;

-- Prevent one business invoice from being linked to multiple drafts.
CREATE UNIQUE INDEX IF NOT EXISTS invoice_intake_drafts_converted_invoice_unique
    ON public.invoice_intake_drafts(converted_invoice_id)
    WHERE converted_invoice_id IS NOT NULL;