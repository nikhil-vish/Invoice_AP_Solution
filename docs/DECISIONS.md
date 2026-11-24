# Product and architecture decisions

- Scope: PO and non-PO invoices; India-based buyers; domestic suppliers; INR; GST where applicable.
- Workflow endpoint: approval routing, not payment execution.
- PO path: PO + line matching + GRN for goods or service acceptance for services, with cumulative invoice reservations.
- Non-PO path: contract/work order/expense authorization + budget + required service/receipt evidence.
- AI assists with document classification, extraction, candidate matching and explanations. Deterministic backend rules own financial controls and decisions.
- Original files are immutable. Every processing attempt has a distinct `processing_runs` record.
- n8n orchestrates integrations; FastAPI owns business logic.
- No automatic supplier creation, bank-detail changes, invoice amount edits or fund transfers.
